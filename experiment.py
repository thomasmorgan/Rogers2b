"""Replicate Rogers' paradox by simulating evolution with people."""

from wallace.experiments import Experiment
from wallace.information import Gene, Meme, State
from wallace.nodes import Source, Agent, Environment
from wallace.networks import DiscreteGenerational
from wallace import processes
from wallace import transformations
from wallace.transformations import Observation
import math
import random


class LearningGene(Gene):
    __mapper_args__ = {"polymorphic_identity": "learning_gene"}


class RogersExperiment(Experiment):

    def __init__(self, session):
        super(RogersExperiment, self).__init__(session)

        self.task = "Rogers network game"
        self.experiment_repeats = 8
        self.practice_repeats = 4
        # note that catch repeats are a subset of experiment repeats!
        self.catch_repeats = 4
        self.practice_difficulty = 0.80
        self.difficulties = [0.50, 0.525, 0.55, 0.575, 0.60, 0.625, 0.65, 0.675, 0.70, 0.725, 0.75, 0.775]*self.experiment_repeats
        self.catch_difficulty = 0.80
        self.min_acceptable_performance = 0.5
        self.network = lambda: DiscreteGenerational(generations=4, generation_size=4, initial_source=True)
        self.environment_type = RogersEnvironment
        self.bonus_payment = 10.00

        self.setup()

        for _ in range(self.catch_repeats):
            random.choice(self.networks(role="experiment")).role = "catch"

        # Setup for first time experiment is accessed

        for net in self.networks():
            if not net.nodes(type=Source):
                source = RogersSource()
                net.add(source)
                self.save(source)
                source.create_information()

        for net in self.networks(role="practice"):
            environment = RogersEnvironment(proportion=self.practice_difficulty)
            net.add(environment)
            self.save(environment)

        for net in self.networks(role="catch"):
            environment = RogersEnvironment(proportion=self.catch_difficulty)
            net.add(environment)
            self.save(environment)

        exp_nets = self.networks(role="experiment")
        for i in range(len(exp_nets)):
            environment = RogersEnvironment(proportion=self.difficulties[i])
            exp_nets[i].add(environment)
            self.save(environment)

    def agent(self, network=None):
        if network.role == "practice" or network.role == "catch":
            return RogersAgentFounder
        elif len(network.nodes(type=Agent)) < network.generation_size:
            return RogersAgentFounder
        else:
            return RogersAgent

    def create_agent_trigger(self, agent, network):
        network.add_agent(agent)
        network.nodes(type=Environment)[0].connect_to(agent)
        current_generation = int(math.floor((len(network.nodes(type=Agent))*1.0-1)/network.generation_size))

        if ((len(network.nodes(type=Agent)) % network.generation_size == 1)
                & (current_generation % 10 == 0)):
            network.nodes(type=Environment)[0].step()

        if (current_generation == 0):
            network.nodes(type=Source)[0].transmit(to_whom=agent)
        else:
            processes.transmit_by_fitness(to_whom=agent, what=Gene, from_whom=Agent)

        agent.receive()

        gene = agent.infos(type=LearningGene)[0].contents
        if (gene == "social"):
            random.choice(agent.neighbors(connection="from", type=Agent)).transmit(what=Meme, to_whom=agent)
        elif (gene == "asocial"):
            network.nodes(type=Environment)[0].transmit(to_whom=agent)
        else:
            raise ValueError("{} has invalid learning gene value of {}".format(agent, gene))

    def transmission_reception_trigger(self, transmissions):
        # Mark transmissions as received
        for t in transmissions:
            t.mark_received()

        for t in transmissions:
            t.destination.update([t.info])

    def information_creation_trigger(self, info):

        agent = info.origin
        agent.calculate_fitness()
        self.save(agent)

    def bonus(self, participant_uuid=None):
        if participant_uuid is None:
            raise(ValueError("You must specify the participant_uuid to calculate the bonus."))

        nodes = []
        for net in self.networks(role="experiment"):
            nodes += [n for n in net.nodes(participant_uuid=participant_uuid)]
        if len(nodes) == 0:
            raise(ValueError("Cannot calculate bonus of participant_uuid {} as there are no nodes associated with this uuid".format(participant_uuid)))
        score = [node.score() for node in nodes]
        average = float(sum(score))/float(len(score))
        bonus = max(0, ((average-0.5)*2))*self.bonus_payment
        return bonus

    def participant_attention_check(self, participant_uuid=None):
        participant_nodes = [net.nodes(participant_uuid=participant_uuid)[0] for net in self.networks(role="catch")]
        scores = [n.score() for n in participant_nodes]
        if participant_nodes:
            avg = sum(scores)/float(len(scores))
        else:
            avg = 1.0
        if avg < self.min_acceptable_performance:
            for net in self.networks():
                for node in net.nodes(participant_uuid=participant_uuid):
                    node.fail()


class RogersSource(Source):
    """A source that initializes agents as asocial learners
    """

    __mapper_args__ = {"polymorphic_identity": "rogers_source"}

    """Sets up all the infos for the source to transmit. Every time it is
    called it should make a new info for each of the two genes."""
    def create_information(self):
        if len(self.infos()) > 1:
            raise Warning("You should tell a RogersSource to create_information more than once!")
        else:
            LearningGene(
                origin=self,
                origin_uuid=self.uuid,
                contents="asocial")

    def _what(self):
        return self.infos(type=LearningGene)[-1]


class RogersAgent(Agent):

    __mapper_args__ = {"polymorphic_identity": "rogers_agent"}

    def calculate_fitness(self):

        if self.fitness is not None:
            raise Exception("You are calculating the fitness of agent {}, ".format(self.uuid) +
                            "but they already have a fitness")
        matches_environment = self.score()

        is_asocial = (self.infos(type=LearningGene)[0].contents == "asocial")
        e = 2
        b = 1
        c = 0.3*b
        baseline = c+0.0001

        self.set_fitness(
            (baseline + matches_environment * b - is_asocial * c) ** e)

    def score(self):
        meme = self.infos(type=Meme)[0]
        state = self.neighbors(connection="from", type=Environment)[0].state(time=meme.creation_time)
        return float(meme.contents) == round(float(state.contents))

    def mutate(self, info_in):
        # If mutation is happening...
        if random.random() < 0.10:
            transformations.mutate(node=self, info_in=info_in, alleles=["social", "asocial"])
        else:
            transformations.replicate(node=self, info_in=info_in)

    def update(self, infos):
        for info_in in infos:
            if isinstance(info_in, LearningGene):
                self.mutate(info_in)


class RogersAgentFounder(RogersAgent):

    __mapper_args__ = {"polymorphic_identity": "rogers_agent_founder"}

    def mutate(self, info_in):
        transformations.replicate(node=self, info_in=info_in)


class SuccessfulObservation(Observation):

    __mapper_args__ = {"polymorphic_identity": "observation_successful"}


class FailedObservation(Observation):

    __mapper_args__ = {"polymorphic_identity": "observation_failed"}


class RogersEnvironment(Environment):

    __mapper_args__ = {"polymorphic_identity": "rogers_environment"}

    def __init__(self, proportion=None):

        if proportion is None:
            raise(ValueError("You need to pass RogersEnvironment a proprtion when you make it."))
        elif random.random() < 0.5:
            proportion = 1 - proportion
        State(
            origin=self,
            origin_uuid=self.uuid,
            contents=proportion)

    def step(self):

        current_state = self.infos(type=State)[-1]
        current_contents = float(current_state.contents)
        transformations.mutate(node=self, info_in=current_state, alleles=[1-current_contents])
