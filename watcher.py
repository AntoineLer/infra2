from pox.core import core
from pox.lib.util import dpid_to_str
from pox.openflow.discovery import Discovery
import pox.openflow.libopenflow_01 as of

log = core.getLogger()


class MyComponent (object):
    def __init__(self):
        def startup():
            core.openflow.addListeners(self)
            core.openflow_discovery.addListeners(self)
        core.call_when_ready(startup, ('openflow','openflow_discovery'))
        log.debug("init over")

    def _handle_LinkEvent(self, event):
        """
        When link changes for example -> link h1 s3 hold_down
        """
        l = event.link
        sw1 = l.dpid1
        sw2 = l.dpid2
        pt1 = l.port1
        pt2 = l.port2

        log.debug(core.openflow_discovery.adjacency)

    def _handle_ConnectionUp(self, event):
        """
        here's a very simple POX component that listens to ConnectionUp events from all switches, and logs a message when one occurs.
        """
        log.debug("Switch %s has come up.", dpid_to_str(event.dpid))
        log.debug("Switch %s has come up.", event.dpid)

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
    core.registerNew(MyComponent)
