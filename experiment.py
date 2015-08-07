"""Replicate Rogers' paradox by simulating evolution with people."""

from wallace.experiments import Experiment
from wallace.information import Gene, Meme, State
from wallace.nodes import Source, Agent, Environment
from wallace.networks import DiscreteGenerational
from wallace.models import Node, Network
from wallace import transformations
from psiturk.models import Participant
from sqlalchemy import Integer, Float
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.sql.expression import cast
from sqlalchemy import and_
import random


class RogersExperiment(Experiment):

    def __init__(self, session):
        super(RogersExperiment, self).__init__(session)

        self.task = "Rogers network game"
        self.verbose = True
        self.experiment_repeats = 120
        self.practice_repeats = 5
        self.catch_repeats = 0  # a subset of experiment repeats
        self.practice_difficulty = 0.80
        self.difficulties = [0.50, 0.5125, 0.525, 0.5375, 0.55, 0.5625, 0.575, 0.5875, 0.60, 0.6125, 0.625, 0.6375, 0.65, 0.6625, 0.675, 0.6875, 0.70]*self.experiment_repeats
        self.catch_difficulty = 0.80
        self.min_acceptable_performance = 0.5
        self.generation_size = 2
        self.network = lambda: DiscreteGenerational(
            generations=20, generation_size=self.generation_size, initial_source=True)
        self.environment_type = RogersEnvironment
        self.bonus_payment = 0
        self.initial_recruitment_size = self.generation_size

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

        participant = Participant.query.filter_by(uniqueid=agent.participant_uuid).one()
        key = participant.uniqueid[0:5]

        num_agents = network.size(type=Agent)
        current_generation = int((num_agents-1)/float(network.generation_size))
        agent.generation = current_generation
        self.log("Agent is {}th agent in network, assigned to generation {}".format(num_agents, current_generation), key)

        self.log("Adding agent to network.", key)
        network.add_agent(agent)
        self.log("Agent added to network", key)

        environment = network.nodes(type=Environment)[0]
        environment.connect(whom=agent)
        self.log("Agent connect to environment", key)

        if (num_agents % network.generation_size == 1
                and current_generation % 10 == 0
                and current_generation != 0):
            self.log("Agent is first in generation and generation is a mutliple of 10: environment stepping", key)
            environment.step()

        if (current_generation == 0):
            self.log("Agent in generation 0: source transmitting to agent", key)
            network.nodes(type=Source)[0].transmit(to_whom=agent)

        agent.receive()

        gene = agent.infos(type=LearningGene)[0].contents
        if (gene == "social"):
            self.log("Agent is a social learner, connecting to social parent", key)
            prev_agents = RogersAgent.query\
                .filter(and_(RogersAgent.failed == False,
                             RogersAgent.network_uuid == network.uuid,
                             RogersAgent.generation == current_generation-1))\
                .all()
            parent = random.choice(prev_agents)
            parent.connect(direction="to", whom=agent)
            parent.transmit(what=Meme, to_whom=agent)
            self.log("Parent transmitting meme to agent", key)
        elif (gene == "asocial"):
            self.log("Agent is an asocial learner: environment transmitting to Agent")
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
        key = "-----"
        self.log("Running Rogers recruit()", key)
        participants = Participant.query.with_entities(Participant.status).all()

        # if all networks are full, close recruitment,
        if not self.networks(full=False):
            self.log("All networks are full, closing recruitment.", key)
            self.recruiter().close_recruitment()

        # if anyone is still working, don't recruit
        elif [p for p in participants if p.status < 100]:
            self.log("Networks not full, but people are still participating: not recruiting.", key)
            pass

        # even if no one else is working, we only need to recruit if the current generation is complete
        elif len([p for p in participants if p.status == 101]) % self.generation_size == 0:
            self.log("Networks not full, no-one currently participating and at end of generation: recruiting another generation.", key)
            self.recruiter().recruit_participants(n=self.generation_size)
        # otherwise do nothing
        else:
            self.log("Networks not full, no-one current participating, but generation not full: not recruiting.", key)
            pass

    def bonus(self, participant=None):
        if participant is None:
            raise(ValueError("You must specify the participant to calculate the bonus."))
        participant_uuid = participant.uniqueid
        key = participant_uuid[0:5]

        nodes = Node.query.join(Node.network)\
                    .filter(and_(Node.participant_uuid == participant_uuid,
                                 Network.role == "experiment"))\
                    .all()
        if len(nodes) == 0:
            self.log("Participant has 0 nodes - cannot calculate bonus!", key)
            return 0
        self.log("calculating bonus...", key)
        score = [node.score for node in nodes]
        average = float(sum(score))/float(len(score))
        bonus = max(0, ((average-0.5)*2))*self.bonus_payment
        self.log("bonus calculated, returning {}".format(bonus), key)
        return bonus

    def participant_attention_check(self, participant=None):

        key = participant.uniqueid[0:5]

        participant_nodes = Node.query.join(Node.network)\
                                .filter(and_(Node.participant_uuid == participant.uniqueid,
                                             Network.role == "catch"))\
                                .all()
        scores = [n.score for n in participant_nodes]

        if participant_nodes:
            self.log("Scoring participant nodes from catch networks", key)
            avg = sum(scores)/float(len(scores))
        else:
            self.log("Participant has no nodes from catch networks, passing by default")
            return True

        is_passing = avg >= self.min_acceptable_performance
        self.log("Min performance is {}. Participant has performance of {}. Returning {}".format(self.min_acceptable_performance, avg, is_passing), key)
        return is_passing

    def check_participant_data(self, participant=None):

        if participant is None:
            raise ValueError("check_participant_data must be passed a participant, not None")

        participant_uuid = participant.uniqueid
        key = participant_uuid[0:5]

        nodes = Node.query.filter_by(participant_uuid=participant_uuid).all()

        if len(nodes) != self.experiment_repeats + self.practice_repeats:
            self.log("Participant has {} nodes - this is not the correct number. Data check failed", key)
            return False

        nets = [n.network_uuid for n in nodes]
        if len(nets) != len(set(nets)):
            self.log("Participant participated in the same network multiple times. Data check failed", key)
            return False

        if None in [n.fitness for n in nodes]:
            self.log("Some of participants nodes are missing a fitness. Data check failed", key)
            return False

        self.log("Data check passed.", key)
        return True


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

    @hybrid_property
    def proportion(self):
        return float(self.property4)

    @proportion.setter
    def proportion(self, proportion):
        self.property4 = repr(proportion)

    @proportion.expression
    def proportion(self):
        return cast(self.property4, Float)

    def calculate_fitness(self):

        from operator import attrgetter

        if self.fitness is not None:
            raise Exception("You are calculating the fitness of agent {}, ".format(self.uuid) +
                            "but they already have a fitness")
        infos = self.infos()

        meme = float([i for i in infos if isinstance(i, Meme)][0].contents)
        proportion = float(max(State.query.filter_by(network_uuid=self.network_uuid).all(), key=attrgetter('creation_time')).contents)
        self.proportion = proportion
        state = round(proportion)

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
