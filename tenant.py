from pox.core import core
import pox.openflow.libopenflow_01 as of
from pox.lib.addresses import EthAddr

class Tenant(object):

    def __init__(self, n_vlans=4, nCore=2):
        if nCore > n_vlans:
            self.nCore = n_vlans
        else:
            self.nCore = nCore

        self.n_vlans = n_vlans
        self.vlans_id = [i for i in range(n_vlans)]
        self.vlans = {}

        self.vlans[EthAddr('00:00:00:00:00:01')] = self.vlans_id[0]
        self.vlans[EthAddr('00:00:00:00:00:02')] = self.vlans_id[1]
        self.vlans[EthAddr('00:00:00:00:00:03')] = self.vlans_id[2]
        self.vlans[EthAddr('00:00:00:00:00:04')] = self.vlans_id[3]

        self.vlans[EthAddr('00:00:00:00:00:05')] = self.vlans_id[0]
        self.vlans[EthAddr('00:00:00:00:00:06')] = self.vlans_id[1]
        self.vlans[EthAddr('00:00:00:00:00:07')] = self.vlans_id[2]
        self.vlans[EthAddr('00:00:00:00:00:08')] = self.vlans_id[3]

        self.vlans[EthAddr('00:00:00:00:00:09')] = self.vlans_id[0]
        self.vlans[EthAddr('00:00:00:00:00:0a')] = self.vlans_id[1]
        self.vlans[EthAddr('00:00:00:00:00:0b')] = self.vlans_id[2]
        self.vlans[EthAddr('00:00:00:00:00:0c')] = self.vlans_id[3]

    def getVlanTranslation(self, EthAddr):
        ID = self.vlans[EthAddr]
        return (self.vlans[EthAddr], (ID % self.nCore) + 1)
