"""Replicate Rogers' paradox by simulating evolution with people."""

from wallace.experiments import Experiment
from wallace.information import Gene, Meme, State
from wallace.nodes import Source, Agent, Environment
from wallace.networks import DiscreteGenerational
from wallace import processes
from wallace import transformations
from sqlalchemy.ext.hybrid import hybrid_property, hybrid_method
from sqlalchemy import and_
import random


class RogersExperiment(Experiment):

    def __init__(self, session):
        super(RogersExperiment, self).__init__(session)

        self.task = "Rogers network game"
        self.experiment_repeats = 120
        self.practice_repeats = 5
        self.catch_repeats = 0  # a subset of experiment repeats
        self.practice_difficulty = 0.80
        self.difficulties = [0.50, 0.525, 0.55, 0.575, 0.60, 0.625, 0.65, 0.675, 0.70, 0.725, 0.75, 0.775]*self.experiment_repeats
        self.catch_difficulty = 0.80
        self.min_acceptable_performance = 0.5
        self.network = lambda: DiscreteGenerational(
            generations=1, generation_size=10, initial_source=True)
        self.environment_type = RogersEnvironment
        self.bonus_payment = 0

        if not self.networks():
            self.setup()

    def setup(self):
        super(RogersExperiment, self).setup()

        for net in random.sample(DiscreteGenerational.query
                                 .with_entities(DiscreteGenerational.role)
                                 .filter_by(role="experiment").all(), self.catch_repeats):
            net.role = "catch"

        for net in self.networks():
            source = RogersSource(network=net)
            source.create_information()
            if net.role == "practice":
                RogersEnvironment(proportion=self.practice_difficulty, network=net)
            if net.role == "catch":
                RogersEnvironment(proportion=self.catch_difficulty, network=net)
            if net.role == "experiment":
                difficulty = self.difficulties[self.networks(role="experiment").index(net)]
                RogersEnvironment(proportion=difficulty, network=net)

    def agent(self, network=None):
        if network.role == "practice" or network.role == "catch":
            return RogersAgentFounder
        elif len(Agent.query.with_entities(Agent.network_uuid).
                 filter_by(network_uuid=network.uuid, status="alive").all()) < network.generation_size:
            return RogersAgentFounder
        else:
            return RogersAgent

    def create_agent_trigger(self, agent, network):
        nuid = network.uuid
        agents = Agent.query.with_entities(Agent.network_uuid).filter_by(network_uuid=nuid, status="alive").all()
        num_agents = len(agents)
        current_generation = int((num_agents-1)/float(network.generation_size))
        agent.generation = current_generation

        network.add_agent(agent)
        environment = Environment.query.filter_by(network_uuid=network.uuid).all()[0]
        environment.connect_to(agent)

        if (num_agents % network.generation_size == 1
                and current_generation % 10 == 0
                and current_generation != 0):
            environment.step()

        if (current_generation == 0):
            network.nodes(type=Source)[0].transmit(to_whom=agent)

        agent.receive()

        gene = LearningGene.query.with_entities(LearningGene.origin_uuid, LearningGene.contents).filter_by(origin_uuid=agent.uuid).all()[-1].contents
        if (gene == "social"):
            prev_agents = RogersAgent.query.filter(and_(RogersAgent.network_uuid == network.uuid, RogersAgent.generation == current_generation-1)).all()
            parent = random.choice(prev_agents)
            parent.connect(direction="to", other_node=agent)
            parent.transmit(what=Meme, to_whom=agent)
        elif (gene == "asocial"):
            environment.transmit(to_whom=agent)
        else:
            raise ValueError("{} has invalid learning gene value of {}".format(agent, gene))

    def transmission_reception_trigger(self, transmissions):
        # Mark transmissions as received
        for t in transmissions:
            t.mark_received()

        for t in transmissions:
            t.destination.update([t.info])

    def information_creation_trigger(self, info):
        info.origin.calculate_fitness()

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


class LearningGene(Gene):
    __mapper_args__ = {"polymorphic_identity": "learning_gene"}

    def _mutated_contents(self):
        alleles = ["social", "asocial"]
        return random.choice([a for a in alleles if a != self.contents])


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
                contents="asocial")

    def _what(self):
        return self.infos(type=LearningGene)[-1]


class RogersAgent(Agent):

    __mapper_args__ = {"polymorphic_identity": "rogers_agent"}

    @hybrid_property
    def generation(self):
        return int(self.property2)

    @generation.setter
    def generation(self, generation):
        self.property2 = repr(generation)

    @generation.expression
    def generation(self):
        return self.property2.label('generation')

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

        self.fitness = (baseline + matches_environment * b - is_asocial * c) ** e

    def score(self):
        meme = self.infos(type=Meme)[0]
        state = self.network.nodes(type=Environment)[0].state(time=meme.creation_time)
        return float(meme.contents) == round(float(state.contents))

    def update(self, infos):
        for info_in in infos:
            if isinstance(info_in, LearningGene):
                if random.random() < 0.10:
                    self.mutate(info_in)
                else:
                    self.replicate(info_in)

    def _what(self):
        return self.infos(type=LearningGene)[0]


class RogersAgentFounder(RogersAgent):

    __mapper_args__ = {"polymorphic_identity": "rogers_agent_founder"}

    def update(self, infos):
        for info in infos:
            if isinstance(info, LearningGene):
                self.replicate(info)


class RogersEnvironment(Environment):

    __mapper_args__ = {"polymorphic_identity": "rogers_environment"}

    def __init__(self, proportion=None, *args, **kwargs):
        super(RogersEnvironment, self).__init__(*args, **kwargs)
        if proportion is None:
            raise(ValueError("You need to pass RogersEnvironment a proprtion when you make it."))
        elif random.random() < 0.5:
            proportion = 1 - proportion
        State(
            origin=self,
            contents=proportion)

    def step(self):

        current_state = self.infos(type=State)[-1]
        current_contents = float(current_state.contents)
        new_contents = 1-current_contents
        info_out = State(origin=self, contents=new_contents)
        transformations.Mutation(info_in=current_state, info_out=info_out)
