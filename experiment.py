"""Replicate Rogers' paradox by simulating evolution with people."""

from wallace.experiments import Experiment
from wallace.information import Gene, Meme, State
from wallace.nodes import Source, Agent, Environment
from wallace.networks import DiscreteGenerational
from wallace.models import Node, Network, Info, Transmission
from wallace import transformations
from psiturk.models import Participant
from sqlalchemy import Integer, Float
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.sql.expression import cast
from sqlalchemy import and_
from json import dumps
import random


class RogersExperiment2b(Experiment):

    def __init__(self, session):
        super(RogersExperiment2b, self).__init__(session)

        self.task = "Rogers network game"
        self.verbose = True
        self.experiment_repeats = 120
        self.practice_repeats = 5
        self.catch_repeats = 12  # a subset of experiment repeats
        self.practice_difficulty = 0.80
        self.difficulties = [0.65]*self.experiment_repeats
        self.social_source_kinds = ["single_agent", "single_generation", "triple_generation"]*(self.experiment_repeats + self.practice_repeats)
        self.catch_difficulty = 0.80
        self.min_acceptable_performance = 10/float(12)
        self.generation_size = 10
        self.network = lambda: DiscreteGenerational(
            generations=12, generation_size=self.generation_size, initial_source=True)
        self.environment_type = RogersEnvironment
        self.bonus_payment = 1.0
        self.initial_recruitment_size = self.generation_size
        self.known_classes["LearningGene"] = LearningGene

        if not self.networks():
            self.setup()
        self.save()

    def setup(self):
        super(RogersExperiment2b, self).setup()

        for net in random.sample(self.networks(role="experiment"), self.catch_repeats):
            net.role = "catch"

        for net in self.networks():
            source = RogersSource(network=net)
            source.create_information()
            social_source = RogersSocialSource(network=net)
            social_source.kind = self.social_source_kinds[self.networks().index(net)]
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
        elif network.size(type=Agent) < 3*network.generation_size:
            return RogersAgentFounder
        else:
            return RogersAgent

    def add_node_to_network(self, participant_id, node, network):

        key = participant_id[0:5]

        num_agents = network.size(type=Agent)
        current_generation = int((num_agents-1)/float(network.generation_size))
        node.generation = current_generation
        self.log("Agent is {}th agent in network, assigned to generation {}".format(num_agents, current_generation), key)

        network.add_node(node)

        node.receive()

        environment = network.nodes(type=Environment)[0]
        environment.connect(whom=node)
        self.log("Agent connect to environment", key)

        gene = node.infos(type=LearningGene)[0].contents
        if (gene == "social"):
            self.log("Agent is a social learner, connecting to social source", key)
            social_source = network.nodes(type=RogersSocialSource)[0]
            social_source.connect(whom=node)
            meme = social_source._what(agent=node)
            social_source.transmit(what=meme, to_whom=node)
        elif (gene == "asocial"):
            environment.transmit(to_whom=node)
        else:
            raise ValueError("{} has invalid learning gene value of {}".format(node, gene))

    def info_post_request(self, participant_id, node, info):
        node.calculate_fitness()

        ts = Transmission.query.filter_by(destination_id=node.id, status="received").with_entities(Transmission.info_id).all()
        infos = Info.query.filter(Info.id.in_([t.info_id for t in ts])).all()
        stimulus = [i for i in infos if type(i) in [State, Meme]][0]
        transformations.Response(info_in=stimulus, info_out=info)

    def submission_successful(self, participant=None):

        key = participant.uniqueid[0:5]

        finished_participants = Participant.query.filter_by(status=101).all()
        num_finished_participants = len(finished_participants)
        current_generation = int((num_finished_participants-1)/float(self.generation_size))

        if num_finished_participants % self.generation_size == 0:
            remainder = (current_generation+1) % 10
            if remainder == 0:
                remainder = 10
            networks = [remainder]
            temp = remainder+10
            while temp < 125:
                networks.append(temp)
                temp = temp+10

            self.log("Participant was final particpant in generation {}: environments {} stepping".format(current_generation, networks), key)
            environments = Environment.query.filter(Environment.id.in_(networks)).all()
            for e in environments:
                e.step()
        else:
            pass

    def recruit(self):
        key = "-----"
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
        participant_id = participant.uniqueid
        key = participant_id[0:5]

        nodes = Node.query.join(Node.network)\
                    .filter(and_(Node.participant_id == participant_id,
                                 Network.role == "experiment"))\
                    .all()
        if len(nodes) == 0:
            self.log("Participant has 0 nodes - cannot calculate bonus!", key)
            return 0
        score = [node.score for node in nodes]
        average = float(sum(score))/float(len(score))
        bonus = round(max(0.0, ((average-0.5)*2))*self.bonus_payment, 2)
        return bonus

    def participant_attention_check(self, participant=None):

        key = participant.uniqueid[0:5]

        participant_nodes = Node.query.join(Node.network)\
                                .filter(and_(Node.participant_id == participant.uniqueid,
                                             Network.role == "catch"))\
                                .all()
        scores = [n.score for n in participant_nodes]

        if participant_nodes:
            avg = sum(scores)/float(len(scores))
        else:
            self.log("Participant has no nodes from catch networks, passing by default", key)
            return True

        is_passing = avg >= self.min_acceptable_performance
        self.log("Min performance is {}. Participant has performance of {}. Returning {}".format(self.min_acceptable_performance, avg, is_passing), key)
        return is_passing

    def check_participant_data(self, participant=None):

        if participant is None:
            raise ValueError("check_participant_data must be passed a participant, not None")

        participant_id = participant.uniqueid
        key = participant_id[0:5]

        nodes = Node.query.filter_by(participant_id=participant_id).all()

        if len(nodes) != self.experiment_repeats + self.practice_repeats:
            self.log("Participant has {} nodes - this is not the correct number. Data check failed".format(len(nodes)), key)
            return False

        nets = [n.network_id for n in nodes]
        if len(nets) != len(set(nets)):
            self.log("Participant participated in the same network multiple times. Data check failed", key)
            return False

        if None in [n.fitness for n in nodes]:
            self.log("Some of participants nodes are missing a fitness. Data check failed", key)
            return False

        if None in [n.score for n in nodes]:
            self.log("Some of participants nodes are missing a score. Data check failed", key)
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


class RogersSocialSource(Source):
    """ A source that sends social information """

    __mapper_args__ = {"polymorphic_identity": "rogers_social_source"}

    @hybrid_property
    def kind(self):
        return self.property1

    @kind.setter
    def kind(self, kind):
        self.property1 = kind

    @kind.expression
    def kind(self):
        return self.property1

    def _what(self, agent=None):
        if agent is None:
            raise ValueError("Rogers Social source _what must be sent a node")
        elif not isinstance(agent, Agent):
            raise ValueError("Rogers social source _what must be sent a node")

        if self.kind == "single_agent":
            parent = random.choice(RogersAgent.query.filter_by(generation=(agent.generation-1), failed=False, network_id=agent.network_id).with_entities(RogersAgent.id).all())
            parents_meme = Meme.query.filter_by(origin_id=parent.id).all()[0]
            new_meme = Meme(origin=self, contents=parents_meme.contents)
            transformations.Replication(info_in=parents_meme, info_out=new_meme)
        elif self.kind == "single_generation":
            generation = RogersAgent.query.filter_by(generation=(agent.generation-1), failed=False, network_id=agent.network_id).with_entities(RogersAgent.id).all()
            ids = [n.id for n in generation]
            memes = Meme.query.filter(Meme.origin_id.in_(ids)).all()
            n_blue = 0
            n_yellow = 0
            for m in memes:
                if m.contents == "blue":
                    n_blue += 1
                elif m.contents == "yellow":
                    n_yellow += 1
                else:
                    raise ValueError("Meme cannot have contents other than yellow or blue, but contents is {}".format(m.contents))
            summary = {"blue": n_blue, "yellow": n_yellow}
            new_meme = Meme(origin=self, contents=dumps(summary))
        elif self.kind == "triple_generation":
            generation1 = RogersAgent.query.filter_by(generation=(agent.generation-1), failed=False, network_id=agent.network_id).with_entities(RogersAgent.id).all()
            generation2 = RogersAgent.query.filter_by(generation=(agent.generation-2), failed=False, network_id=agent.network_id).with_entities(RogersAgent.id).all()
            generation3 = RogersAgent.query.filter_by(generation=(agent.generation-3), failed=False, network_id=agent.network_id).with_entities(RogersAgent.id).all()
            ids1 = [n.id for n in generation1]
            ids2 = [n.id for n in generation2]
            ids3 = [n.id for n in generation3]
            memes1 = Meme.query.filter(Meme.origin_id.in_(ids1)).all()
            memes2 = Meme.query.filter(Meme.origin_id.in_(ids2)).all()
            memes3 = Meme.query.filter(Meme.origin_id.in_(ids3)).all()
            n_blue1 = 0
            n_yellow1 = 0
            n_blue2 = 0
            n_yellow2 = 0
            n_blue3 = 0
            n_yellow3 = 0
            for m in memes1:
                if m.contents == "blue":
                    n_blue1 += 1
                elif m.contents == "yellow":
                    n_yellow1 += 1
                else:
                    raise ValueError("Meme cannot have contents other than yellow or blue, but contents is {}".format(m.contents))
            for m in memes2:
                if m.contents == "blue":
                    n_blue2 += 1
                elif m.contents == "yellow":
                    n_yellow2 += 1
                else:
                    raise ValueError("Meme cannot have contents other than yellow or blue, but contents is {}".format(m.contents))
            for m in memes3:
                if m.contents == "blue":
                    n_blue3 += 1
                elif m.contents == "yellow":
                    n_yellow3 += 1
                else:
                    raise ValueError("Meme cannot have contents other than yellow or blue, but contents is {}".format(m.contents))
            summary = {"blue1": n_blue1, "yellow1": n_yellow1, "blue2": n_blue2, "yellow2": n_yellow2, "blue3": n_blue3, "yellow3": n_yellow3}
            new_meme = Meme(origin=self, contents=dumps(summary))
        else:
            raise ValueError("Rogers social source cannot be {}".format(self.kind))
        return new_meme


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
            raise Exception("You are calculating the fitness of agent {}, ".format(self.id) +
                            "but they already have a fitness")
        infos = self.infos()

        said_blue = ([i for i in infos if isinstance(i, Meme)][0].contents == "blue")
        proportion = float(max(State.query.filter_by(network_id=self.network_id).all(), key=attrgetter('creation_time')).contents)
        self.proportion = proportion
        is_blue = proportion > 0.5

        if said_blue is is_blue:
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
