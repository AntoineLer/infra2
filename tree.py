from pox.core import core
from pox.lib.util import dpid_to_str
from pox.openflow.discovery import Discovery
import pox.openflow.libopenflow_01 as of
from pox.lib.revent import *
from clostopo import ClosTopo

log = core.getLogger()


class Switch(EventMixin):
    """
        The switch object represents a switch, its connection and contains
    a boolean isCore if the switch is whether a Core or not.
    """

    def __init__(self):
        self.connection = None
        self.dpid = None
        self._listener = None
        self.isCore = None
        self.mac_to_port = {}

    def connect(self, connection, topo):
        """Connect the switch with the controller.

        Args:
            connection: Connection with the controller
            topo: The topology of the network
        """
        if self.dpid is None:
            self.dpid = connection.dpid
        assert self.dpid == connection.dpid
        self.isCore = topo.isCoreSwitch('s' + str(self.dpid))
        self.disconnect()
        self.connection = connection
        self._listeners = self.listenTo(connection)

    def disconnect(self):
        """Disconnect the switch with the controller.

        Args: /
        """
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

        Args:
            packet_in: the ofp_packet_in object the switch had sent
            out_port: The port in which the packet will be sent
        """
        msg = of.ofp_packet_out()
        msg.data = packet_in

        # Add an action to send to the specified port
        action = of.ofp_action_output(port=out_port)
        msg.actions.append(action)

        # Send message to switch
        self.connection.send(msg)

    def act_like_switch(self, packet, packet_in):
        """
        Implement switch-like behavior with simple spanning tree policy.

        Args:
            packet: Parsed packet data
            packet_in: the ofp_packet_in object the switch had sent
        """

        #log.debug("Packet in Switch s" + str(self.dpid) + "\n")
        """keep the port corresponding to the source MAC address"""
        self.mac_to_port[packet.src] = packet_in.in_port

        """if the destination is known"""
        if packet.dst in self.mac_to_port:
            """resend packet to the good port"""
            self.resend_packet(packet_in, self.mac_to_port[packet.dst])
            #log.debug("Installing flow...")
            #log.debug("Source MAC: " + str(packet.src))
            #log.debug("Destination MAC: " + str(packet.dst))
            #log.debug("Out port: " + str(self.mac_to_port[packet.dst]) + "\n")
            """install a permanent flow matching the destination of the packet with the good port"""
            msg = of.ofp_flow_mod()
            msg.match = of.ofp_match(dl_dst=packet.dst)
            msg.idle_timeout = of.OFP_FLOW_PERMANENT
            msg.hard_timeout = of.OFP_FLOW_PERMANENT
            msg.buffer_id = packet_in.buffer_id
            action = of.ofp_action_output(port=self.mac_to_port[packet.dst])
            msg.actions.append(action)
            self.connection.send(msg)
        else:
            """if the destination is unknow, flood"""
            self.resend_packet(packet_in, of.OFPP_FLOOD)

    def _handle_PacketIn(self, event):
        """
        Handles packet in messages from the switch.

        Args:
            event: The event
        """
        packet = event.parsed  # This is the parsed packet data.
        if not packet.parsed:
            log.warning("Ignoring incomplete packet")
            return

        packet_in = event.ofp  # The actual ofp_packet_in message.
        self.act_like_switch(packet, packet_in)

    def disable_flooding(self, port):
        """
        Disable flooding to a port of the switch.

        Args:
            port: The port
        """
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
        self.root = None  # Will be the main switch Core

        def startup():
            """Start events"""
            core.openflow.addListeners(self)
            core.openflow_discovery.addListeners(self)
        core.call_when_ready(startup, ('openflow', 'openflow_discovery'))

    def _handle_LinkEvent(self, event):
        """
        Handles changes or discovery between switches.

        Args:
            event: The event
        """
        link = event.link
        switch_1 = self.switches.get(link.dpid1)
        switch_2 = self.switches.get(link.dpid2)
        port_1 = link.port1
        port_2 = link.port2

        """ disable flooding between Edge and Core Switches"""
        if switch_1.isCore and self.root.dpid is not switch_1.dpid:
            switch_2.disable_flooding(port_2)
        elif switch_2.isCore and self.root.dpid is not switch_2.dpid:
            switch_1.disable_flooding(port_1)
        #log.debug("PLEASE FONCTIONNE")

    def _handle_ConnectionUp(self, event):
        """
        here's a very simple POX component that listens to ConnectionUp events from all switches,
        and create a switch object there is no existing yet.

        Args:
            event: The event
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

        if self.root is None and switch.isCore:
            self.root = switch
        elif switch.isCore and switch.dpid < self.root.dpid:
            self.root_dpid = switch.dpid
            self.root = switch

    def _handle_ConnectionDown(self, event):
        """
        here's a very simple POX component that listens to ConnectionDown events from all switches,
        and disconnect a switch object.

        Args:
            event: The event
        """
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

        Args:
            event: The event
        """
        if event.added:
            action = "added"
        elif event.deleted:
            action = "removed"
        else:
            action = "modified"


def launch(nCore=2, nEdge=3, nHosts=3, bw=10):
    """
    Launch the POX Controller.

    Args:
        nCore: The number of core switch
        nEdge: The number of edge switch
        nHosts: The number of hosts per edge
        bw: The bandwidth of each link
    """
    core.registerNew(Tree, int(nCore), int(nEdge), int(nHosts), int(bw))
