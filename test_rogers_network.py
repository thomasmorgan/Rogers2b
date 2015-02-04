from wallace import networks, agents, db, sources
from experiment import RogersNetwork, RogersNetworkProcess, RogersSource, RogersAgent


class TestNetworks(object):

    def setup(self):
        self.db = db.init_db(drop_all=True)

    def teardown(self):
        self.db.rollback()
        self.db.close()

    def test_create_rogers_network_small(self):
        net = RogersNetwork(agents.ReplicatorAgent, self.db, agents_per_generation=3)

        newcomers = []
        for i in range(12):
            agent = agents.ReplicatorAgent()
            newcomers.append(agent)
            net.add_agent(agent)

        assert not newcomers[0].has_connection_to(newcomers[6])
        assert not newcomers[0].has_connection_to(newcomers[7])
        assert not newcomers[0].has_connection_to(newcomers[8])

        assert newcomers[0].has_connection_to(newcomers[3])
        assert newcomers[0].has_connection_to(newcomers[4])
        assert newcomers[0].has_connection_to(newcomers[5])

        assert newcomers[11].has_connection_from(newcomers[6])
        assert newcomers[11].has_connection_from(newcomers[7])
        assert newcomers[11].has_connection_from(newcomers[8])

        assert len(net.vectors) == 30

    def test_rogers_network_process(self):

        # Create the network and process.
        net = RogersNetwork(RogersAgent, self.db,
                            agents_per_generation=3)
        process = RogersNetworkProcess(net)

        # Add a source.
        source = RogersSource()
        net.add_source_global(source)
        print "Added initial source: " + str(source)

        for i in range(12):
            agent = RogersAgent()
            net.add_agent(agent)
            process.step()
