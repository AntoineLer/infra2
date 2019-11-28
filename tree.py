from pox.core import core
from pox.lib.util import dpid_to_str
from pox.openflow.discovery import Discovery
import pox.openflow.libopenflow_01 as of
from pox.lib.revent import *
from clostopo import ClosTopo

log = core.getLogger()

blocked = False

class Switch(EventMixin):

    def __init__(self):
        self.connection = None
        self.dpid = None
        self._listener = None
        self.isCore = None
        self.mac_to_port = {}

    def connect(self, connection, topo):
        if self.dpid is None:
            self.dpid = connection.dpid
        assert self.dpid == connection.dpid
        self.isCore = topo.isCoreSwitch('s' + str(self.dpid))
        self.disconnect()
        self.connection = connection
        self._listeners = self.listenTo(connection)

    def disconnect(self):
        if self.connection is not None:
            log.debug("Disconnect %s" % (self.connection,))
            self.connection.removeListeners(self._listeners)
            self.connection = None
            self._listeners = None

    def resend_packet(self, packet_in, out_port):
        """
        Instructs the switch to resend a packet that it had sent to us.
        "packet_in" is the ofp_packet_in object the switch had sent to the
        controller due to a table-miss.
        """
        msg = of.ofp_packet_out()
        msg.data = packet_in

        # Add an action to send to the specified port
        action = of.ofp_action_output(port = out_port)
        msg.actions.append(action)

        # Send message to switch
        self.connection.send(msg)

    def act_like_switch(self, packet, packet_in):
        """
        Implement switch-like behavior.
        """

        # Here's some pseudocode to start you off implementing a learning
        # switch.  You'll need to rewrite it as real Python code.

        # Learn the port for the source MAC
        log.debug("\n")
        self.mac_to_port[packet.src] = packet_in.in_port
        log.debug(str(self.mac_to_port))  
        log.debug("ID SWITCH: " + str(self.dpid))

        if packet.dst in self.mac_to_port:
            # Send packet out the associated port
            # self.resend_packet(packet_in, self.mac_to_port[packet.dst])
            # Once you have the above working, try pushing a flow entry
            # instead of resending the packet (comment out the above and
            # uncomment and complete the below.)

            # Maybe the log statement should have source/destination/port?
            log.debug("Installing flow...")
            log.debug("Source MAC: " + str(packet.src))
            log.debug("Destination MAC: " + str(packet.dst))
            log.debug("Packet out port: " + str(self.mac_to_port[packet.dst]) + "\n")

            msg = of.ofp_flow_mod()
            #
            # Set fields to match received packet
            msg.match = of.ofp_match.from_packet(packet)
            #
            # < Set other fields of flow_mod (timeouts? buffer_id?) >
            #msg.idle_timeout = 30
            #msg.hard_timeout = 60
            msg.buffer_id = packet_in.buffer_id
            action = of.ofp_action_output(port=self.mac_to_port[packet.dst])
            msg.actions.append(action)
            # log.debug(str(msg))
            #
            # < Add an output action, and send -- similar to resend_packet() >
            self.connection.send(msg)

        else:
            # Flood the packet out everything but the input port
            # This part looks familiar, right?
            self.resend_packet(packet_in, of.OFPP_FLOOD)

    def _handle_PacketIn(self, event):
        """
        Handles packet in messages from the switch.
        """

        packet = event.parsed  # This is the parsed packet data.
        if not packet.parsed:
            log.warning("Ignoring incomplete packet")
            return

        packet_in = event.ofp  # The actual ofp_packet_in message.

        # Comment out the following line and uncomment the one after
        # when starting the exercise.
        # self.act_like_hub(packet, packet_in)
        self.act_like_switch(packet, packet_in)

    def disable_flooding(self, port):
        msg = of.ofp_port_mod(
            port_no=port, hw_addr=self.connection.ports[port].hw_addr, config=of.OFPPC_NO_FLOOD, mask=of.OFPPC_NO_FLOOD)
        self.connection.send(msg)


class Tree (object):
    def __init__(self, nCore=2, nEdge=3, nHosts=3, bw=10):
        self.topo = ClosTopo(nCore, nEdge, nHosts, bw)
        self.nCore = nCore
        self.nEdge = nEdge
        self.nHost = nEdge * nHosts
        self.switches = {}
        def startup():
            core.openflow.addListeners(self)
            core.openflow_discovery.addListeners(self)
        core.call_when_ready(startup, ('openflow', 'openflow_discovery'))

    def _handle_LinkEvent(self, event):
        """
        When link changes for example -> link h1 s3 hold_down
        """
        link = event.link
        switch_1 = self.switches.get(link.dpid1)
        switch_2 = self.switches.get(link.dpid2)
        port_1 = link.port1
        port_2 = link.port2
        if (switch_1.isCore and ('s' + str(switch_1.dpid) is not 's1')) or (switch_2.isCore and ('s' + str(switch_2.dpid) is not 's1')): #faire une variable ou quoi pour désigner le root core (modifier clostopo ?) 
            switch_1.disable_flooding(port_1)
            switch_2.disable_flooding(port_2)           

        #if 's' + str(switch_1.dpid) == 's2' or 's' + str(switch_2.dpid) == 's2':
        #    switch_1.disable_flooding(port_1)
        #    switch_2.disable_flooding(port_2)  
        #log.debug("PLEASE FONCTIONNE")
        # log.debug(core.openflow_discovery.adjacency)

    def _handle_ConnectionUp(self, event):
        """
        here's a very simple POX component that listens to ConnectionUp events from all switches, and logs a message when one occurs.
        """
        log.debug("New Switch Connection")
        switch = self.switches.get(event.dpid)
        if switch is None:
            # New switch
            switch = Switch()
            self.switches[event.dpid] = switch
            switch.connect(event.connection, self.topo)
        else:
            switch.connect(event.connection, self.topo)

    def _handle_ConnectionDown(self, event):
        log.debug("Switch Deconnection")
        switch = self.switches.get(event.dpid)
        if switch is None:
            log.debug("Should never happen please")
        else:
            switch.disconnect()
        log.debug("switch " + dpid_to_str(event.dpid) + " down")
        # Bonus here

    def _handle_PortStatus(self, event):
        """
        PortStatus events are raised when the controller receives an OpenFlow port-status message (ofp_port_status) from a switch,
        which indicates that ports have changed.  Thus, its .ofp attribute is an ofp_port_status.
        """
        if event.added:
            action = "added"
        elif event.deleted:
            action = "removed"
        else:
            action = "modified"
        print "Port %s on Switch %s has been %s." % (event.port, event.dpid, action)


def launch(nCore=2, nEdge=3, nHosts=3, bw=10):
    core.registerNew(Tree, int(nCore), int(nEdge), int(nHosts), int(bw))
