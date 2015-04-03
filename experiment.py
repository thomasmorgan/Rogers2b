"""Replicate Rogers' paradox by simulating evolution with people."""

from wallace.agents import Agent
from wallace.environments import Environment
from wallace.experiments import Experiment
from wallace.information import Gene, Meme, State
from wallace.models import Info
from wallace.networks import Network
from wallace.processes import Process
from wallace.recruiters import PsiTurkRecruiter
from wallace.sources import Source
from wallace.transformations import Mutation, Observation
import math
import random
from sqlalchemy import desc


class LearningGene(Gene):
    __mapper_args__ = {"polymorphic_identity": "learning_gene"}


class RogersExperiment(Experiment):

    def __init__(self, session):
        super(RogersExperiment, self).__init__(session)

        self.task = "Rogers network game"
        self.num_repeats = 4
        self.network_type = RogersNetwork
        self.environment_type = RogersEnvironment
        self.process_type = RogersNetworkProcess
        self.recruiter = PsiTurkRecruiter

        # Get a list of all the networks, creating them if they don't already
        # exist.
        self.networks = Network.query.all()
        if not self.networks:
            for i in range(self.num_repeats):
                net = self.network_type()
                self.session.add(net)
        self.networks = Network.query.all()

        # Setup for first time experiment is accessed
        for net in self.networks:
            if not net.sources:
                source = RogersSource()
                self.session.add(source)
                environment = RogersEnvironment()
                environment.network = net
                self.session.add(environment)
                self.session.commit()
                net.add_source(source)
                source.create_information()
                self.session.commit()

    def agent_type_generator(self, network=None):
        if len(network.agents) < network.num_agents_per_generation:
            return RogersAgentFounder
        else:
            return RogersAgent

    def transmission_reception_trigger(self, transmissions):
        # Mark transmissions as received
        for t in transmissions:
            t.mark_received()

        for t in transmissions:
            t.destination.update([t.info])

    def information_creation_trigger(self, info):

        agent = info.origin
        agent.calculate_fitness()
        self.session.add(agent)
        self.session.commit()

        if self.is_experiment_over():
            # If the experiment is over, stop recruiting and export the data.
            self.recruiter().close_recruitment(self)
        else:
            # Otherwise recruit a new participant.
            self.recruiter().recruit_new_participants(self, n=1)

    def is_network_full(self, network):
        return len(network.agents) >= network.num_agents


class RogersSource(Source):
    """A source that initializes agents as asocial learners
    """

    __mapper_args__ = {"polymorphic_identity": "rogers_source"}

    """Sets up all the infos for the source to transmit. Every time it is
    called it should make a new info for each of the two genes."""
    def create_information(self):
        LearningGene(
            origin=self,
            origin_uuid=self.uuid,
            contents="asocial")

    def _what(self):
        return LearningGene\
            .query\
            .filter_by(origin_uuid=self.uuid)\
            .order_by(desc(Info.creation_time))\
            .first()


class RogersNetwork(Network):
    """In a Rogers Network agents are arranged into generations of a set size
    and each agent is connected to all agents in the previous generation (the
    first generation agents are connected to a source)
    """

    __mapper_args__ = {"polymorphic_identity": "rogers"}

    @property
    def num_agents_per_generation(self):
        return 2

    @property
    def num_generations(self):
        return 2

    @property
    def num_agents(self):
        return self.num_agents_per_generation * self.num_generations

    def first_agent(self):
        if len(self.agents) > 0:
            return self.get_nodes(type=Agent)[0]
        else:
            return None

    @property
    def last_agent(self):
        if len(self.agents) > 0:
            return self.get_nodes(type=Agent)[-1]
        else:
            return None

    def add_agent(self, newcomer):

        newcomer.network = self

        # Place them in the network.
        if len(self.agents) <= self.num_agents_per_generation:
            self.sources[0].connect_to(newcomer)
        else:
            newcomer_generation = math.floor(((len(self.agents)-1)*1.0)/self.num_agents_per_generation)
            min_previous_generation = int((newcomer_generation-1)*self.num_agents_per_generation)
            previous_generation_agents = self.get_nodes(type=Agent)[min_previous_generation:(min_previous_generation+self.num_agents_per_generation)]

            newcomer.connect_from(previous_generation_agents)

        # Connect the newcomer and environment
        self.get_nodes(type=Environment)[0].connect_to(newcomer)
 
    def agents_of_generation(self, generation):
        first_index = generation*self.num_agents_per_generation
        last_index = first_index+(self.num_agents_per_generation)
        return self.agents[first_index:last_index]


class RogersNetworkProcess(Process):

    def __init__(self, network):
        self.network = network
        self.environment = self.network.get_nodes(type=Environment)[0]

        # Environment\
        #     .query\
        #     .filter_by(network=network)\
        #     .one()
        super(RogersNetworkProcess, self).__init__(network)

    def step(self, verbose=True):

        current_generation = int(math.floor((len(self.network.get_nodes(type=Agent))*1.0-1)/self.network.num_agents_per_generation))

        if (len(self.network.get_nodes(type=Agent)) % self.network.num_agents_per_generation) == 1:
            self.environment.step()

        newcomer = self.network.get_nodes(type=Agent)[-1]

        if (current_generation == 0):
            self.network.get_nodes(type=Source)[0].transmit(to_whom=newcomer)
        else:
            parent = None
            potential_parents = newcomer.get_upstream_nodes(type=RogersAgent)
            potential_parent_fitnesses = [p.fitness for p in potential_parents]
            potential_parent_probabilities = [(f/(1.0*sum(potential_parent_fitnesses))) for f in potential_parent_fitnesses]

            rnd = random.random()
            temp = 0.0
            for i, probability in enumerate(potential_parent_probabilities):
                temp += probability
                if temp > rnd:
                    parent = potential_parents[i]
                    break

            parent.transmit(what=Gene, to_whom=newcomer)

        newcomer.receive_all()

        if (newcomer.get_info(type=LearningGene)[0].contents == "social"):
            rnd = random.randint(0, (self.network.num_agents_per_generation-1))
            cultural_parent = potential_parents[rnd]
            cultural_parent.transmit(what=Meme, to_whom=newcomer)
            # newcomer.receive_all()
        elif (newcomer.get_info(type=LearningGene)[0].contents == "asocial"):
            # Observe the environment.
            newcomer.observe(self.environment)
        else:
            raise AssertionError("Learner gene set to non-coherent value")


class RogersAgent(Agent):

    __mapper_args__ = {"polymorphic_identity": "rogers_agent"}

    def calculate_fitness(self):

        if self.fitness is not None:
            print "You are calculating the fitness of agent {}, ".format(self.uuid) +\
                "but they already have a fitness"

        state = State\
            .query\
            .order_by(desc(Info.creation_time))\
            .first()

        try:
            matches_environment = (self.meme.contents == state.contents)
        except Exception, e:
            matches_environment = False
            print "Warning! Calculating the fitness of a meme-less agent!"
            print "Setting meme to wrong answer for test's sake"
        is_asocial = (self.learning_gene.contents == "asocial")

        e = 2
        b = 20
        c = 9
        baseline = 10

        self.fitness = (
            baseline + matches_environment * b - is_asocial * c) ** e

    @property
    def learning_gene(self):
        gene = LearningGene\
            .query\
            .filter_by(origin_uuid=self.uuid)\
            .order_by(desc(Info.creation_time))\
            .first()
        return gene

    @property
    def meme(self):
        meme = Meme\
            .query\
            .filter_by(origin_uuid=self.uuid)\
            .order_by(desc(Info.creation_time))\
            .first()
        return meme

    def mutate(self, info_in):
        # If mutation is happening...
        if random.random() < 0.50:

            # Create a new info based on the old one.
            strats = ["social", "asocial"]
            new_contents = strats[not strats.index(info_in.contents)]
            info_out = LearningGene(origin=self, contents=new_contents)

            # Register the transformation.
            Mutation(
                info_out=info_out,
                info_in=info_in,
                node=self)

        else:
            self.replicate(info_in)

    def update(self, infos):
        for info_in in infos:

            if isinstance(info_in, LearningGene):
                self.mutate(info_in)


class RogersAgentFounder(RogersAgent):

    __mapper_args__ = {"polymorphic_identity": "rogers_agent_founder"}

    def mutate(self, info_in):
        self.replicate(info_in)


class SuccessfulObservation(Observation):

    __mapper_args__ = {"polymorphic_identity": "observation_successful"}


class FailedObservation(Observation):

    __mapper_args__ = {"polymorphic_identity": "observation_failed"}


class RogersEnvironment(Environment):

    __mapper_args__ = {"polymorphic_identity": "rogers_environment"}

    def __init__(self):

        try:
            assert(len(State.query.filter_by(origin=self).all()))
        except Exception:
            State(
                origin=self,
                origin_uuid=self.uuid,
                contents=True)

    def step(self):

        if random.random() < 0.10:
            current_state = (self.state.contents == "True")
            State(
                origin=self,
                origin_uuid=self.uuid,
                contents=str(not current_state))
