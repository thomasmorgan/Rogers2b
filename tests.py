from wallace import networks, agents, db, sources, information, models, environments
from experiment import RogersNetwork, RogersNetworkProcess, RogersSource, RogersAgent, RogersAgentFounder, RogersEnvironment, RogersExperiment, LearningGene
from nose.tools import raises, assert_raises
import os


class TestNetworks(object):

    def setup(self):
        self.db = db.init_db(drop_all=True)


    def teardown(self):
        self.db.rollback()
        self.db.close()
        # os.remove('wallace.db')

    def add(self, *args):
        self.db.add_all(args)
        self.db.commit()

    def test_create_rogers_network_small(self):

        exp = RogersExperiment(self.db)
        net = RogersNetwork()

        source = RogersSource()
        net.add(source)
        self.db.add(source)
        source.create_information()

        environment = RogersEnvironment()
        net.add(environment)
        self.db.add(environment)

        new_agents = []
        for i in range(16):
            new_agents.append(exp.agent_type_generator(net)())
            self.db.add(new_agents[-1])
            net.add_agent(new_agents[-1])

        for within_g in range(3):
            for g in range(2):
                assert new_agents[4*g + within_g].has_connection_to(new_agents[4*(g+1) + within_g])

        for a in range(3):
            assert source.has_connection_to(new_agents[a])

        for a in new_agents:
            assert environment in a.get_upstream_nodes()

        for a in source.get_downstream_nodes():
            assert isinstance(a, RogersAgentFounder)

            for a in new_agents:
                if isinstance(a, RogersAgentFounder):
                    assert len(a.get_upstream_nodes()) == 2
                    assert source in a.get_upstream_nodes()
                    assert environment in a.get_upstream_nodes()
                elif isinstance(a, RogersAgent):
                    assert len(a.get_upstream_nodes()) == 5
                    assert environment in a.get_upstream_nodes()


    # def test_rogers_network_process(self):

    #     n = 100
    #     apg = 100

    #     environment = RogersEnvironment()
    #     state = information.State(
    #         origin=environment,
    #         contents="True")
    #     self.add(environment, state)

    #     # Create the network and process.
    #     net = RogersNetwork()

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

    def test_rogers_process(self):

        exp = RogersExperiment(self.db)
        net = exp.networks[0]

        for i in range(net.num_generations):
            for j in range(net.num_agents_per_generation):
                newcomer_type = exp.agent_type_generator(network=net)

                newcomer = newcomer_type()
                self.db.add(newcomer)
                net.add_agent(newcomer)
                exp.process_type(net).step()
            
                assert len(newcomer.get_transmissions(type="incoming", status="pending")) == 1
                gene = newcomer.get_infos(type=LearningGene)[0].contents
                if gene == "asocial":
                    assert isinstance(newcomer.get_transmissions(type="incoming", status="pending")[-1].info, information.State)
                else:
                    assert isinstance(newcomer.get_transmissions(type="incoming", status="pending")[-1].info, information.Meme)

                newcomer.receive_all()

                information.Meme(
                origin=newcomer,
                origin_uuid=newcomer.uuid,
                contents=1)
                newcomer.calculate_fitness()

        self.db.commit()

    def test_rogers_bonus(self):

        # self.teardown()
        # self.setup()

        exp = RogersExperiment(self.db)

        for i in range(exp.num_repeats_practice + exp.num_repeats_experiment):
            agent = RogersAgent()
            agent.participant_uuid = "tom"
            agent2 = RogersAgent()
            agent2.participant_uuid = "jordan"
            agent3 = RogersAgent()
            agent3.participant_uuid = "wallace"
            net = exp.networks[i]
            net.add([agent, agent2, agent3])
            self.db.add_all([agent, agent2, agent3])

            net.get_nodes(type=environments.Environment)[0].connect_to([agent, agent2, agent3])

            information.State(
                origin=net.get_nodes(type=environments.Environment)[0],
                origin_uuid=net.get_nodes(type=environments.Environment)[0].uuid,
                contents=1)

            information.Meme(
                origin=agent,
                origin_uuid=agent.uuid,
                contents=1)

            information.Meme(
                origin=agent2,
                origin_uuid=agent2.uuid,
                contents=0)

            information.State(
                origin=net.get_nodes(type=environments.Environment)[0],
                origin_uuid=net.get_nodes(type=environments.Environment)[0].uuid,
                contents=0)

            information.Meme(
                origin=agent3,
                origin_uuid=agent3.uuid,
                contents=0)

            information.State(
                origin=net.get_nodes(type=environments.Environment)[0],
                origin_uuid=net.get_nodes(type=environments.Environment)[0].uuid,
                contents=2)

        assert exp.bonus(participant_uuid="tom") == 10.00
        assert exp.bonus(participant_uuid="jordan") == 0.00
        assert exp.bonus(participant_uuid="wallace") == 10.00

        assert_raises(ValueError, exp.bonus, participant_uuid="liam") 
        assert_raises(ValueError, exp.bonus) 






