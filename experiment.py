"""Replicate Rogers' paradox by simulating evolution with people."""

from wallace.environments import Environment
from wallace.experiments import Experiment
from wallace.information import Gene, Meme, State
from wallace.models import Source, Agent
from wallace.networks import Network, DiscreteGenerational
from wallace.processes import Process
from wallace.transformations import Mutation, Observation
import math
import random


class LearningGene(Gene):
    __mapper_args__ = {"polymorphic_identity": "learning_gene"}


class RogersExperiment(Experiment):

    def __init__(self, session):
        super(RogersExperiment, self).__init__(session)

        self.task = "Rogers network game"
        self.num_repeats_experiment = 4
        self.num_repeats_practice = 4
        self.difficulties = [0.50, 0.525, 0.55, 0.575, 0.60, 0.625, 0.65, 0.675, 0.70, 0.725, 0.75, 0.775]
        self.practice_difficulties = [0.80]
        self.network = lambda: RogersDiscreteGenerational()
        self.environment_type = RogersEnvironment
        self.process = RogersNetworkProcess
        self.bonus_payment = 10.00

        self.setup()

        # Setup for first time experiment is accessed
        self.proportions = ((self.practice_difficulties*self.num_repeats_practice)[0:self.num_repeats_practice] +
                            (self.difficulties*self.num_repeats_experiment)[0:self.num_repeats_experiment])
        for i in range(len(self.networks)):
            net = self.networks[i]
            if not net.nodes(type=Source):
                source = RogersSource()
                net.add(source)
                self.save(source)
                source.create_information()

                environment = RogersEnvironment(proportion=self.proportions[i])
                net.add(environment)
                self.save(environment)

    def agent(self, network=None):
        index = self.networks.index(network)
        if index < self.num_repeats_practice:
            return RogersAgentFounder
        elif len(network.nodes(type=Agent)) < network.generation_size:
            return RogersAgentFounder
        else:
            return RogersAgent

    def create_agent_trigger(self, agent, network):
        network.add_agent(agent)
        network.nodes(type=Environment)[0].connect_to(agent)
        self.process(network).step()

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

    def participant_completion_trigger(self):

        if self.is_experiment_over():
            # If the experiment is over, stop recruiting and export the data.
            self.recruiter().close_recruitment(self)
        else:
            # Otherwise recruit a new participant.
            self.recruiter().recruit_new_participants(self, n=1)

    def bonus(self, participant_uuid=None):
        if participant_uuid is not None:
            nodes_lists = [net.nodes_of_participant(participant_uuid) for net in self.networks[self.num_repeats_practice:]]
            nodes = [node for sublist in nodes_lists for node in sublist]
            if len(nodes) == 0:
                raise(ValueError("Cannot calculate bonus of participant_uuid {} as there are no nodes associated with this uuid".format(participant_uuid)))
            score = [node.score() for node in nodes]
            return (float(sum(score))/float(len(score)))*self.bonus_payment
        else:
            raise(ValueError("You must specify the participant_uuid to calculate the bonus."))


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


class RogersDiscreteGenerational(DiscreteGenerational):

    __mapper_args__ = {"polymorphic_identity": "rogers_discrete-generational"}

    @property
    def generations(self):
        return 4

    @property
    def generation_size(self):
        return 4


class RogersNetworkProcess(Process):

    def __init__(self, network):
        self.network = network
        self.environment = self.network.nodes(type=Environment)[0]

    def step(self, verbose=True):

        current_generation = int(math.floor((len(self.network.nodes(type=Agent))*1.0-1)/self.network.generation_size))

        if ((len(self.network.nodes(type=Agent)) % self.network.generation_size == 1)
                & (current_generation % 10 == 0)):
            self.environment.step()

        newcomer = self.network.nodes(type=Agent)[-1]

        if (current_generation == 0):
            self.network.nodes(type=Source)[0].transmit(to_whom=newcomer)
        else:
            parent = None
            potential_parents = newcomer.upstream_nodes(type=RogersAgent)
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

        if (newcomer.infos(type=LearningGene)[0].contents == "social"):
            rnd = random.randint(0, (self.network.generation_size-1))
            cultural_parent = potential_parents[rnd]
            cultural_parent.transmit(what=Meme, to_whom=newcomer)
        elif (newcomer.infos(type=LearningGene)[0].contents == "asocial"):
            newcomer.observe(self.environment)
        else:
            raise AssertionError("Learner gene set to non-coherent value")


class RogersAgent(Agent):

    __mapper_args__ = {"polymorphic_identity": "rogers_agent"}

    def calculate_fitness(self):

        if self.fitness is not None:
            raise Exception("You are calculating the fitness of agent {}, ".format(self.uuid) +
                            "but they already have a fitness")

        environment = self.upstream_nodes(type=Environment)[0]
        state = self.observe(environment)
        self.receive(state)

        matches_environment = self.score()

        is_asocial = (self.infos(type=LearningGene)[0].contents == "asocial")
        e = 2
        b = 1
        c = 0.3*b
        baseline = c+0.0001

        self.fitness = (
            baseline + matches_environment * b - is_asocial * c) ** e

    def score(self):
        meme = self.infos(type=Meme)[0]
        state = self.upstream_nodes(type=Environment)[0].state(time=meme.creation_time)
        return float(meme.contents) == round(float(state.contents))

    def mutate(self, info_in):
        # If mutation is happening...
        if random.random() < 0.10:

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
        new_state = State(
            origin=self,
            origin_uuid=self.uuid,
            contents=str(1 - float(current_state.contents)))
        Mutation(
            info_out=new_state,
            info_in=current_state,
            node=self)
