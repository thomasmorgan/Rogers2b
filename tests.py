from wallace import networks, agents, db, sources, information, models
from experiment import RogersNetwork, RogersNetworkProcess, RogersSource, RogersAgent, RogersAgentFounder, RogersEnvironment, RogersExperiment


class TestNetworks(object):

    def setup(self):
        self.db = db.init_db(drop_all=True)

    def teardown(self):
        self.db.rollback()
        self.db.close()

    def add(self, *args):
        self.db.add_all(args)
        self.db.commit()

    # def test_create_rogers_network_small(self):

    #     environment = RogersEnvironment(self.db)
    #     state = information.State(
    #         origin=environment,
    #         contents="True")
    #     self.add(environment, state)

    #     net = RogersNetwork(agents.ReplicatorAgent, self.db, agents_per_generation=3)
    #     newcomers = []
    #     for i in range(12):
    #         agent = agents.ReplicatorAgent()
    #         newcomers.append(agent)
    #         net.add_agent(agent)

    #     assert not newcomers[0].has_connection_to(newcomers[6])
    #     assert not newcomers[0].has_connection_to(newcomers[7])
    #     assert not newcomers[0].has_connection_to(newcomers[8])

    #     assert newcomers[0].has_connection_to(newcomers[3])
    #     assert newcomers[0].has_connection_to(newcomers[4])
    #     assert newcomers[0].has_connection_to(newcomers[5])

    #     assert newcomers[11].has_connection_from(newcomers[6])
    #     assert newcomers[11].has_connection_from(newcomers[7])
    #     assert newcomers[11].has_connection_from(newcomers[8])

    #     assert len(net.vectors) == 30

    # def test_rogers_network_process(self):

    #     n = 100
    #     apg = 100

    #     environment = RogersEnvironment(self.db)
    #     state = information.State(
    #         origin=environment,
    #         contents="True")
    #     self.add(environment, state)

    #     # Create the network and process.
    #     net = RogersNetwork(RogersAgent, self.db,
    #                         agents_per_generation=apg)

    #     process = RogersNetworkProcess(net, environment)

    #     # Add a source.
    #     source = RogersSource()
    #     source.create_information()
    #     net.add_source_global(source)

    #     for i in range(n):
    #         if i < apg:
    #             agent = RogersAgentFounder()
    #         else:
    #             agent = RogersAgent()
    #         net.add_agent(agent)
    #         process.step()

    def test_agent_type(self):

        exp = RogersExperiment(self.db)

        net = exp.networks[0]

        f = []
        p = []

        for i in range(net.num_generations):
            for j in range(net.num_agents_per_generation):
                print i*net.num_agents_per_generation + j
                newcomer_type = exp.agent_type_generator(network=net)

                newcomer = newcomer_type()
                self.db.add(newcomer)
                self.db.commit()

                net.add_agent(newcomer)
                self.db.commit()

                # print newcomer.predecessors2

                # print exp.networks[0].sources[0]
                # print newcomer
                # print net.vectors

                # print exp.networks[0].sources[0].has_connection_to(newcomer)
                # print exp.networks[0].sources[0].successors2

                exp.process_type(net).step()

            f.append(net.average_fitness(generation=i))
            p.append(net.proportion_social_learners(generation=i))

            print f
            print p

        self.db.commit()
