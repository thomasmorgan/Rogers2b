"""Replicate Rogers' paradox by simulating evolution with people."""

from wallace.experiments import Experiment
from wallace.information import Gene, Meme, State
from wallace.nodes import Source, Agent, Environment
from wallace.networks import DiscreteGenerational
from wallace.models import Node, Network
from wallace import transformations
from psiturk.models import Participant
from sqlalchemy import Integer
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.sql.expression import cast
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
        self.difficulties = [0.50, 0.5125, 0.525, 0.5375, 0.55, 0.5625, 0.575, 0.5875, 0.60, 0.6125, 0.625, 0.6375, 0.65, 0.6625, 0.675, 0.6875, 0.70]*self.experiment_repeats
        self.catch_difficulty = 0.80
        self.min_acceptable_performance = 0.5
        self.generation_size = 20
        self.network = lambda: DiscreteGenerational(
            generations=1, generation_size=self.generation_size, initial_source=True)
        self.environment_type = RogersEnvironment
        self.bonus_payment = 0

        if not self.networks():
            self.setup()
        self.save()

    def setup(self):
        super(RogersExperiment, self).setup()

        for net in random.sample(self.networks(role="experiment"), self.catch_repeats):
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
        elif network.size(type=Agent) < network.generation_size:
            return RogersAgentFounder
        else:
            return RogersAgent

    def create_agent_trigger(self, agent, network):
        num_agents = network.size(type=Agent)
        current_generation = int((num_agents-1)/float(network.generation_size))
        agent.generation = current_generation

        network.add_agent(agent)
        environment = network.nodes(type=Environment)[0]
        environment.connect(whom=agent)

        if (num_agents % network.generation_size == 1
                and current_generation % 10 == 0
                and current_generation != 0):
            environment.step()

        if (current_generation == 0):
            network.nodes(type=Source)[0].transmit(to_whom=agent)

        agent.receive()

        gene = agent.infos(type=LearningGene)[0].contents
        if (gene == "social"):
            prev_agents = RogersAgent.query\
                .filter(and_(RogersAgent.failed == False,
                             RogersAgent.network_uuid == network.uuid,
                             RogersAgent.generation == current_generation-1))\
                .all()
            parent = random.choice(prev_agents)
            parent.connect(direction="to", whom=agent)
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

    def recruit(self):
        """Recruit participants to the experiment as needed."""

        networks = Network.query.with_entities(Network.full).all()
        agents = RogersAgent.query\
            .with_entities(RogersAgent.network_uuid, RogersAgent.participant_uuid)\
            .filter(RogersAgent.failed == False)\
            .all()

        # If all networks are full, close recruitment.
        if all([net.full for net in networks]):
            self.recruiter().close_recruitment()
        else:
            # Determine if the current generation is full
            at_end_of_generation = all([
                len([a for a in agents if a.network_uuid == net.uuid])
                % net.generation_size == 0 for net in networks])

            # Figure out if all non-failed participants have finished
            participant_uuids = set([a.participant_uuid for a in agents])
            participants = Participant.query\
                .with_entities(Participant.status)\
                .filter(Participant.uuid.in_(participant_uuids))\
                .all()
            all_nodes_finished = all([p.status >= 4 for p in participants])

        # # If all networks are full, close recruitment.
        # if not self.networks(full=False):
        #     self.recruiter().close_recruitment()
        # else:
        #     # Figure out if we've filled up the whole generation.
        #     at_end_of_generation = all([(net.size(type=Agent) % net.generation_size) == 0 for net in self.networks])

        #     # Figure out if all the current nodes are associated with
        #     # participants who finished the task.
        #     nodes = Node.query.with_entities(Node.participant_uuid).filter(Node.failed==False).all()
        #     participant_uuids = set([n.participant_uuid for n in nodes])
        #     participants = Participant.query.filter(Participant.uuid.in_(participant_uuids)).all()
        #     all_nodes_finished = all([p.status >= 4 for p in participants])

            # Recruit a new generation's worth of participants.
            if at_end_of_generation and all_nodes_finished:
                self.recruiter().recruit_participants(n=self.generation_size)

    def bonus(self, participant_uuid=None):
        if participant_uuid is None:
            raise(ValueError("You must specify the participant_uuid to calculate the bonus."))

        nodes = Node.query.join(Node.network)\
                    .filter(and_(Node.participant_uuid == participant_uuid,
                                 Network.role == "experiment"))\
                    .all()
        if len(nodes) == 0:
            raise(ValueError("Cannot calculate bonus of participant_uuid {} as there are no nodes associated with this uuid".format(participant_uuid)))
        score = [node.score for node in nodes]
        average = float(sum(score))/float(len(score))
        bonus = max(0, ((average-0.5)*2))*self.bonus_payment
        return bonus

    def participant_attention_check(self, participant_uuid=None):
        participant_nodes = Node.query.join(Node.network)\
                                .filter(and_(Node.participant_uuid == participant_uuid,
                                             Network.role == "catch"))\
                                .all()
        scores = [n.score for n in participant_nodes]

        if participant_nodes:
            avg = sum(scores)/float(len(scores))
        else:
            avg = 1.0

        is_passing = avg >= self.min_acceptable_performance

        if not is_passing:
            for node in Node.query.filter_by(participant_uuid=participant_uuid).all():
                node.fail()

            self.recruiter().recruit_participants(n=1)

        return is_passing


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
        if len(self.infos()) == 0:
            LearningGene(
                origin=self,
                contents="asocial")

    def _what(self):
        return self.infos(type=LearningGene)[0]


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
        return cast(self.property2, Integer)

    @hybrid_property
    def score(self):
        return int(self.property3)

    @score.setter
    def score(self, score):
        self.property3 = repr(score)

    @score.expression
    def score(self):
        return cast(self.property3, Integer)

    def calculate_fitness(self):

        from operator import attrgetter

        if self.fitness is not None:
            raise Exception("You are calculating the fitness of agent {}, ".format(self.uuid) +
                            "but they already have a fitness")
        infos = self.infos()

        meme = float([i for i in infos if isinstance(i, Meme)][0].contents)
        state = round(float(max(State.query.filter_by(network_uuid=self.network_uuid).all(), key=attrgetter('creation_time')).contents))

        if meme == state:
            self.score = 1
        else:
            self.score = 0

        is_asocial = [i for i in infos if isinstance(i, LearningGene)][0].contents == "asocial"
        e = 2
        b = 1
        c = 0.3*b
        baseline = c+0.0001

        self.fitness = (baseline + self.score * b - is_asocial * c) ** e

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

        from operator import attrgetter

        current_state = max(self.infos(type=State), key=attrgetter('creation_time'))
        current_contents = float(current_state.contents)
        new_contents = 1-current_contents
        info_out = State(origin=self, contents=new_contents)
        transformations.Mutation(info_in=current_state, info_out=info_out)
