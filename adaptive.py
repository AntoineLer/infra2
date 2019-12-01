from pox.core import core
from pox.lib.util import dpid_to_str
from pox.openflow.discovery import Discovery
import pox.openflow.libopenflow_01 as of
from pox.lib.revent import *
from clostopo import ClosTopo
from pox.lib.recoco import Timer

log = core.getLogger()

class Switch(EventMixin):

    def __init__(self):
        self.connection = None
        self.dpid = None
        self._listener = None
        self.isCore = None
        self.mac_to_port = {}
        self.edgeToCore = {}
        Timer(3, self._timer_func, recurring=True)
        self.current_bw = {}
        self.total_bw = {}

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
            #log.debug("Disconnect %s" % (self.connection,))
            self.connection.removeListeners(self._listeners)
            self.connection = None
            self._listeners = None
            self.total_bw = {}
            self.current_bw = {}

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
        action = of.ofp_action_output(port = out_port)
        msg.actions.append(action)

        # Send message to switch
        self.connection.send(msg)


    def act_like_switch(self, packet, packet_in):
        """
        Implement switch-like behavior with adaptive policy.

        Args:
            packet: Parsed packet data
            packet_in: the ofp_packet_in object the switch had sent
        """
        #log.debug("Packet in Switch s" + str(self.dpid))

        """if the switch is core"""
        if self.isCore:

            """keep the port corresponding to the source MAC address"""
            self.mac_to_port[packet.src] = packet_in.in_port

            """if the destination is known"""
            if packet.dst in self.mac_to_port:
                """resend the packet to the good port"""
                self.resend_packet(packet_in, self.mac_to_port[packet.dst])
                #log.debug("Installing flow...")
                #log.debug("Source MAC: " + str(packet.src))
                #log.debug("Destination MAC: " + str(packet.dst))
                #log.debug("Out port: " + str(self.mac_to_port[packet.dst]) + "\n")

                """install a permanent flow matching the destination of the packet with the good port"""
                msg = of.ofp_flow_mod()
                msg.match = of.ofp_match(dl_dst = packet.dst)
                msg.idle_timeout = of.OFP_FLOW_PERMANENT
                msg.hard_timeout = of.OFP_FLOW_PERMANENT
                action = of.ofp_action_output(port=self.mac_to_port[packet.dst])
                msg.actions.append(action)
                self.connection.send(msg)
            else:
                """if the destination is unknow, flood"""
                self.resend_packet(packet_in, of.OFPP_FLOOD)
        else:
            """if the switch is edge,
            keep the port corresponding to the source MAC address"""
            self.mac_to_port[packet.src] = packet_in.in_port

            """if the destination is known"""
            if packet.dst in self.mac_to_port:
                """resend the packet to the good port"""
                self.resend_packet(packet_in, self.mac_to_port[packet.dst])
                #log.debug("Installing flow...")
                #log.debug("Source MAC: " + str(packet.src))
                #log.debug("Destination MAC: " + str(packet.dst))
                #log.debug("Out port: " + str(self.mac_to_port[packet.dst]) + "\n")

                """install a flow with perfect match that lasts few seconds"""
                msg = of.ofp_flow_mod() #Push rule in table
                msg.match = of.ofp_match.from_packet(packet)
                msg.idle_timeout = 3
                msg.hard_timeout = 10
                action = of.ofp_action_output(port=self.mac_to_port[packet.dst])
                msg.actions.append(action)
                self.connection.send(msg)
                """remove the mac_to_port entry used to install the flow"""
                del self.mac_to_port[packet.dst]
            else:
                """if the destination is unknown"""
                """flood"""
                self.resend_packet(packet_in, of.OFPP_FLOOD)

                """if the packet comes from a host"""
                if packet_in.in_port not in self.edgeToCore.values():
                    """send the packet to the less loaded core"""
                    port = min(self.current_bw, key=self.current_bw.get)
                    self.resend_packet(packet_in, port)

                    #log.debug("PORT MATCH LOL: " + str(port))
                    #log.debug(self.current_bw)


    def push_flow(self, packet, packet_in, port, idle_timeout=of.OFP_FLOW_PERMANENT, hard_timeout=of.OFP_FLOW_PERMANENT):
        """
        Add flow in the switch table.

        Args:
            src: The source Ethernet frame
            dst: The destination Ethernet frame
            idle_timeout: /
            hard_timeout: /
        """
        self.resend_packet(packet_in, port)
        #log.debug("Installing flow...")
        #log.debug("Source MAC: " + str(packet.src))
        #log.debug("Destination MAC: " + str(packet.dst))
        #log.debug("Out port: " + str(port) + "\n")

        msg = of.ofp_flow_mod() #Push rule in table
        msg.match = of.ofp_match.from_packet(packet)
        msg.idle_timeout = idle_timeout
        msg.hard_timeout = hard_timeout
        msg.buffer_id = packet_in.buffer_id
        action = of.ofp_action_output(port=port)
        msg.actions.append(action)
        self.connection.send(msg)

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

    def add_edge_to_core(self, port, coreDpid):
        """
        Maintains ports that are connections between Edge and Core.

        Args:
            port: The port connected to Switch
            coreDpid: the DPID of the Switch
        """
        #log.debug("Edge Switch " + str(self.dpid) + " Learns Vlan translation with core Switch " + str(coreDpid))
        self.edgeToCore[coreDpid] = port

    def disable_flooding(self, port):
        """
        Disable flooding to a port of the switch.

        Args:
            port: The port
        """
        msg = of.ofp_port_mod(
            port_no=port, hw_addr=self.connection.ports[port].hw_addr, config=of.OFPPC_NO_FLOOD, mask=of.OFPPC_NO_FLOOD)
        self.connection.send(msg)

    def enable_flooding(self, port):
        """
        Enable flooding to a port of the switch.

        Args:
            port: The port
        """
        msg = of.ofp_port_mod(port_no = port,
                              hw_addr = self.connection.ports[port].hw_addr,
                              config = 0, # opposite of of.OFPPC_NO_FLOOD,
                              mask = of.OFPPC_NO_FLOOD)
        self.connection.send(msg)

    def _timer_func (self):
        """
        Recurring function to request stats from switches
        for each connection (which represents a switch actually)
        request statistics
        """
        if self.connection is not None:
            self.connection.send(of.ofp_stats_request(body=of.ofp_port_stats_request()))

    def _handle_PortStatsReceived(self, event):
        """
        handles PortStatus
        """
        if not self.isCore:
            stats = event.stats
            for portStat in stats:
                if portStat.port_no in self.edgeToCore.values():
                    try:
                        old_bw = self.total_bw[portStat.port_no]
                    except:
                        old_bw = 0
                    self.total_bw[portStat.port_no] = portStat.rx_bytes + portStat.tx_bytes
                    self.current_bw[portStat.port_no] = (self.total_bw[portStat.port_no] - old_bw)/3

class Adaptive(object):
    def __init__(self, nCore=2, nEdge=3, nHosts=3, bw=10):
        self.topo = ClosTopo(nCore, nEdge, nHosts, bw)
        self.nCore = nCore
        self.nEdge = nEdge
        self.nHost = nEdge * nHosts
        self.switches = {}
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
        if switch_1.isCore and not switch_2.isCore:
            switch_2.disable_flooding(port_2)
            switch_2.add_edge_to_core(port_2, switch_1.dpid)
        elif switch_2.isCore and not switch_1.isCore:
            switch_1.disable_flooding(port_1)
            switch_1.add_edge_to_core(port_1, switch_2.dpid)

    def _handle_ConnectionUp(self, event):
        """
        here's a very simple POX component that listens to ConnectionUp events from all switches,
        and create a switch object there is no existing yet.

        Args:
            event: The event
        """
        #log.debug("New Switch Connection")
        switch = self.switches.get(event.dpid)
        if switch is None:
            # New switch
            switch = Switch()
            self.switches[event.dpid] = switch
            switch.connect(event.connection, self.topo)
        else:
            switch.connect(event.connection, self.topo)

    def _handle_ConnectionDown(self, event):
        """
        here's a very simple POX component that listens to ConnectionDown events from all switches,
        and disconnect a switch object.

        Args:
            event: The event
        """
        #log.debug("Switch Deconnection")
        switch = self.switches.get(event.dpid)
        if switch is None:
            #log.debug("Should never happen please")
            return
        else:
            switch.disconnect()
        #log.debug("switch " + dpid_to_str(event.dpid) + " down")
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

        #print "Port %s on Switch %s has been %s." % (event.port, event.dpid, action)

def launch(nCore=2, nEdge=3, nHosts=3, bw=10):
    """
    Launch the POX Controller.

    Args:
        nCore: The number of core switch
        nEdge: The number of edge switch
        nHosts: The number of hosts per edge
        bw: The bandwidth of each link
    """
    core.registerNew(Adaptive, nCore=int(nCore), nEdge=int(nEdge), nHosts=int(nHosts), bw=int(bw))
