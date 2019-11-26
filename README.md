# Second Assignment

LOL

## ofp_packet_out - Sending packets from the switch

The main purpose of this message is to instruct a switch to send a packet (or enqueue it).  However it can also be useful as a way to instruct a switch to discard a buffered packet (by simply not specifying any actions).

## ofp_flow_mod - Flow table modification

	Markup : * idle_timeout (int) - rule will expire if it is not matched in 'idle_timeout' seconds. A value of OFP_FLOW_PERMANENT means there is no idle_timeout (the default).
		 * hard_timeout (int) - rule will expire after 'hard_timeout' seconds. A value of OFP_FLOW_PERMANENT means it will never expire (the default)
		 * buffer_id (int) - A buffer on the datapath that the new flow will be applied to.  Use None for none.  Not meaningful for flow deletion.
		 * out_port (int) - This field is used to match for DELETE commands.OFPP_NONE may be used to indicate that there is no restriction.
		 * actions (list) - actions are defined below, each desired action object is then appended to this list and they are executed in order.
		 * match (ofp_match) - the match structure for the rule to match on (see below).	