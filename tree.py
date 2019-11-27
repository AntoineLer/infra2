from pox.core import core
from pox.lib.util import dpid_to_str
from pox.openflow.discovery import Discovery
import pox.openflow.libopenflow_01 as of
from pox.lib.revent import *

log = core.getLogger()

class Switch(EventMixin):

    def __init__(self):
        self.connection = None
        self.dpid = None
        self._listener = None
        self.mac_to_port = {}

    def connect(self, connection):
        if self.dpid is None:
            self.dpid = connection.dpid
        assert self.dpid == connection.dpid
        self.disconnect()
        self.connection = connection
        self._listeners = self.listenTo(connection)

    def disconnect (self):
        if self.connection is not None:
            log.debug("Disconnect %s" % (self.connection,))
            self.connection.removeListeners(self._listeners)
            self.connection = None
            self._listeners = None

    def _handle_PacketIn (self, event):
        log.debug("New Packet in switch" + dpid_to_str(self.dpid))

class Tree (object):
    def __init__(self):
        self.switches = {}
        def startup():
            core.openflow.addListeners(self)
            core.openflow_discovery.addListeners(self)
        core.call_when_ready(startup, ('openflow','openflow_discovery'))

    def _handle_LinkEvent(self, event):
        """
        When link changes for example -> link h1 s3 hold_down
        """
        l = event.link
        sw1 = l.dpid1
        sw2 = l.dpid2
        pt1 = l.port1
        pt2 = l.port2

        #log.debug(core.openflow_discovery.adjacency)

    def _handle_ConnectionUp(self, event):
        """
        here's a very simple POX component that listens to ConnectionUp events from all switches, and logs a message when one occurs.
        """
        log.debug("test")
        switch = self.switches.get(event.dpid)
        if switch is None:
            # New switch
            switch = Switch()
            self.switches[event.dpid] = switch
            switch.connect(event.connection)
        else:
            switch.connect(event.connection)

    def _handle_ConnectionDown(self, event):
        log.debug("AIE")

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


def launch():
    core.registerNew(Tree)
