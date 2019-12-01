from pox.core import core
from pox.lib.util import dpid_to_str
from pox.openflow.discovery import Discovery
import pox.openflow.libopenflow_01 as of
from pox.lib.revent import *
from clostopo import ClosTopo
from tenant import Tenant
from pox.lib.addresses import EthAddr

log = core.getLogger()


class Switch(EventMixin):
    """The switch object represents a switch, its connection, contains a Tenant
    for Vlans and a boolean isCore if the switch is whether a Core or not.
    """

    def __init__(self, tenant):
        self.connection = None
        self.dpid = None
        self._listener = None
        self.isCore = None
        self.mac_to_port = {}
        self.edgeToCore = {}#Contains port connection edge and core
        self.tenant = tenant

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
        Implement switch-like behavior with Vlans policy.

        Args:
            packet: Parsed packet data
            packet_in: the ofp_packet_in object the switch had sent
        """
        #log.debug("Packet in Switch s" + str(self.dpid))

        """If the destination mac address is known"""
        if packet.dst in self.mac_to_port:
            #log.debug("Dst " + str(packet.dst) + " known in the switch")
            if self.isCore:
                """
                If the switch is a core, update mac_to_port dict with the in port,
                then install flow in the two directions : packet.src <----> packet.dst
                """
                #log.debug("Current switch is a Core")
                self.mac_to_port[packet.src] = packet_in.in_port
                #log.debug("install flow between src <----> dst")
                self.install_flow(
                    packet.src, packet.dst, self.mac_to_port[packet.dst], idle_timeout=of.OFP_FLOW_PERMANENT, hard_timeout=of.OFP_FLOW_PERMANENT)
                self.install_flow(
                    packet.dst, packet.src, self.mac_to_port[packet.src], idle_timeout=of.OFP_FLOW_PERMANENT, hard_timeout=of.OFP_FLOW_PERMANENT)
                """If the core switch is not corresponding with the right vlan_id, stop here"""
                (vlan_id, coreDPID) = self.tenant.getVlanTranslation(packet.src)
                if coreDPID is not self.dpid:
                    #log.debug("Not good vlan id, but installed flows anyway")
                    #log.debug("End treating packet\n")
                    return
            else:
                """If the switch is a edge"""
                #log.debug("Current switch is a Edge")
                if packet_in.in_port in self.edgeToCore.values():
                    """
                    If the packet comes from a Core Switch, install flow in the
                    direction packet.src ----> packet.dst,
                    then, install and forced flow of a host (packet.dst here) to the right core given its vlan_id
                    """
                    #log.debug("Packet received from a Core Switch")
                    #log.debug("install flow src ----> dst")
                    self.install_flow(
                        packet.src, packet.dst, self.mac_to_port[packet.dst], idle_timeout=of.OFP_FLOW_PERMANENT, hard_timeout=of.OFP_FLOW_PERMANENT)
                    #log.debug("install flow host ----> corresponding vlan core")
                    (vlan_id, coreDPID) = self.tenant.getVlanTranslation(packet.dst)
                    self.install_flow(
                        packet.dst, packet.src, self.edgeToCore[coreDPID], idle_timeout=of.OFP_FLOW_PERMANENT, hard_timeout=of.OFP_FLOW_PERMANENT)
                else:
                    """
                    If the packet comes from a host, update mac_to_port dict with the in port,
                    then install flow in the two directions : packet.src <----> packet.dst
                    """
                    #log.debug("Packet received from a host")
                    self.mac_to_port[packet.src] = packet_in.in_port
                    #log.debug("install flow between src <----> dst")
                    self.install_flow(
                        packet.src, packet.dst, self.mac_to_port[packet.dst], idle_timeout=of.OFP_FLOW_PERMANENT, hard_timeout=of.OFP_FLOW_PERMANENT)
                    self.install_flow(
                        packet.dst, packet.src, self.mac_to_port[packet.src], idle_timeout=of.OFP_FLOW_PERMANENT, hard_timeout=of.OFP_FLOW_PERMANENT)
            """Resend Packet"""
            self.resend_packet(packet_in, self.mac_to_port[packet.dst])
        else:
            """If the destination mac address is not known"""
            #log.debug("dst " + str(packet.dst) + " not known in the switch")
            if self.isCore:
                """If the switch is a core, update mac_to_port dict with the in port"""
                #log.debug("Current switch is a Core")
                self.mac_to_port[packet.src] = packet_in.in_port

                """If the core switch is not corresponding with the right vlan_id, stop here"""
                (vlan_id, coreDPID) = self.tenant.getVlanTranslation(packet.src)
                if coreDPID is not self.dpid:
                    #log.debug("Not good vlan id, but maintains info anyway")
                    #log.debug("End treating packet\n")
                    return
                """resend packet"""
                self.resend_packet(packet_in, of.OFPP_FLOOD)
            else:
                """If the switch is a Edge"""
                #log.debug("Current switch is a Edge")
                if packet_in.in_port in self.edgeToCore.values():
                    """If the packet comes from a Core Switch, simply flood to hosts"""
                    #log.debug("Packet received from a Core Switch")
                    self.resend_packet(packet_in, of.OFPP_FLOOD)
                else:
                    """If the packet comes from a hosts, simply flood to hosts and all Core Switches"""
                    #log.debug("Packet received from a host")
                    self.mac_to_port[packet.src] = packet_in.in_port
                    self.resend_packet(packet_in, of.OFPP_FLOOD)
                    for dpid in self.edgeToCore:
                        self.resend_packet(packet_in, self.edgeToCore[dpid])
        #log.debug("End treating packet\n")

    def install_flow(self, src, dst, port, idle_timeout=15, hard_timeout=30):
        """
        Add flow in the switch table.

        Args:
            src: The source Ethernet frame
            dst: The destination Ethernet frame
            idle_timeout: /
            hard_timeout: /
        """
        #log.debug("Installing flow...")
        #log.debug("Source MAC: " + str(src))
        #log.debug("Destination MAC: " + str(dst))
        #log.debug("Out port: " + str(port))
        msg = of.ofp_flow_mod()  # Push rule in table
        msg.match = of.ofp_match(dl_src=src, dl_dst=dst)
        msg.idle_timeout = idle_timeout
        msg.hard_timeout = hard_timeout
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

    def add_vlan_rule(self, port, coreDpid):
        """
        If the switch if a Edge, it maintains ports that are connected to Core Switches.

        Args:
            port: The port connected to a Core Switch
            coreDpid: the DPID of the Core Switch
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
        msg = of.ofp_port_mod(port_no=port,
                              hw_addr=self.connection.ports[port].hw_addr,
                              config=0,  # opposite of of.OFPPC_NO_FLOOD,
                              mask=of.OFPPC_NO_FLOOD)
        self.connection.send(msg)


class Vlans(object):
    """The vlan class"""

    def __init__(self, tenant, nCore=2, nEdge=3, nHosts=3, bw=10):
        self.topo = ClosTopo(nCore, nEdge, nHosts, bw)#The topology of the network
        self.nCore = nCore
        self.nEdge = nEdge
        self.nHost = nEdge * nHosts
        self.switches = {}
        self.tenant = tenant#Tenant for the vlans policy

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
            switch_2.add_vlan_rule(port_2, switch_1.dpid)
        elif switch_2.isCore and not switch_1.isCore:
            switch_1.disable_flooding(port_1)
            switch_1.add_vlan_rule(port_1, switch_2.dpid)

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
            switch = Switch(self.tenant)
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
            return
            #log.debug("Should never happen please")
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
        print "Port %s on Switch %s has been %s." % (event.port, event.dpid, action)


def launch(nCore=2, nEdge=3, nHosts=3, bw=10, n_vlans=4):
    """
    Launch the POX Controller.

    Args:
        nCore: The number of core switch
        nEdge: The number of edge switch
        nHosts: The number of hosts per edge
        bw: The bandwidth of each link
        n_vlans: The number of vlans id
    """
    tenant = Tenant(int(n_vlans), int(nCore))
    core.registerNew(Vlans, tenant, nCore=int(nCore),
                     nEdge=int(nEdge), nHosts=int(nHosts), bw=int(bw))
