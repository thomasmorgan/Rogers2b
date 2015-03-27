"""Replicate Rogers' paradox by simulating evolution with people."""

from wallace.agents import Agent
from wallace.environments import Environment
from wallace.experiments import Experiment
from wallace.information import Gene, Meme, State
from wallace.models import Info, Vector
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


class MutationGene(Gene):
    __mapper_args__ = {"polymorphic_identity": "mutation_gene"}


class RogersExperiment(Experiment):

    def __init__(self, session):
        super(RogersExperiment, self).__init__(session)

        self.task = "Rogers network game"
        self.num_agents_per_generation = 20
        self.num_generations = 20
        self.num_agents = self.num_agents_per_generation * self.num_generations
        self.environment = RogersEnvironment(self.session)
        self.num_agents = self.num_agents_per_generation*self.num_generations
        self.network = RogersNetwork(self.agent_type_generator, self.session, self.num_agents_per_generation, self.num_generations)
        self.process = RogersNetworkProcess(self.network, self.environment)
        self.recruiter = PsiTurkRecruiter

        # Setup for first time experiment is accessed
        if not self.network.sources:
            source = RogersSource()
            self.network.add_source_global(source)
            source.create_information()

    def agent_type_generator(self):
        if len(self.network.agents) < self.num_agents_per_generation:
            return RogersAgentFounder
        else:
            return RogersAgent

    def newcomer_arrival_trigger(self, newcomer):

        self.network.add_agent(newcomer)

        # Run the next step of the process.
        self.process.step()

    def transmission_reception_trigger(self, transmissions):
        # Mark transmissions as received
        for t in transmissions:
            t.mark_received()

    def information_creation_trigger(self, info):

        agent = info.origin
        self.network.db.add(agent)

        if self.is_experiment_over():
            # If the experiment is over, stop recruiting and export the data.
            self.recruiter().close_recruitment()
        else:
            # Otherwise recruit a new participant.
            self.recruiter().recruit_new_participants(self, n=self.num_agents_per_generation)

    def is_experiment_over(self):
        return len(self.network.agents) == self.num_agents


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

    def __init__(self, agent_type_generator, db, agents_per_generation=10, num_generations=10):
        self.db = db
        self.agents_per_generation = agents_per_generation
        self.num_generations = num_generations
        super(RogersNetwork, self).__init__(agent_type_generator, db)

    def proportion_social_learners(self, generation=None):

        is_social_learner = [
            a.learning_gene.contents == "social" for a in self.agents_of_generation(generation)]

        return 1.0 * sum(is_social_learner) / len(is_social_learner)

    def average_fitness(self, generation=None):

        fitnesses = [
            float(a.fitness) for a in self.agents_of_generation(generation)]

        return sum(fitnesses) / len(fitnesses)

    def first_agent(self):
        if len(self.agents) > 0:
            return self.db.query(Agent)\
                .order_by(Agent.creation_time)\
                .filter(Agent.status != "failed")\
                .first()
        else:
            return None

    @property
    def last_agent(self):
        if len(self.agents) > 0:
            return self.db.query(Agent)\
                .order_by(Agent.creation_time.desc())\
                .filter(Agent.status != "failed")\
                .first()
        else:
            return None

    def add_agent(self, newcomer):
        if len(self.sources) is 0:
            self.db.add(RogersSource())

        self.db.add(newcomer)

        # Place them in the network.
        if len(self.agents) <= self.agents_per_generation:
            self.sources[0].connect_to(newcomer)
        else:
            newcomer_generation = math.floor(((len(self.agents)-1)*1.0)/self.agents_per_generation)
            min_previous_generation = (newcomer_generation-1)*self.agents_per_generation
            previous_generation_agents = self.db.query(Agent)\
                .filter(Agent.status != "failed")\
                .order_by(Agent.creation_time)[min_previous_generation:(min_previous_generation+self.agents_per_generation)]

            for a in previous_generation_agents:
                a.connect_to(newcomer)

        # Connect the newcomer and environment
        environment = Environment.query.first()
        environment.connect_to(newcomer)
        print environment

        return newcomer

    def agents_of_generation(self, generation):
        first_index = generation*self.agents_per_generation
        last_index = first_index+(self.agents_per_generation)
        return self.agents[first_index:last_index]


class RogersNetworkProcess(Process):

    def __init__(self, network, environment):
        self.network = network
        self.environment = environment
        super(RogersNetworkProcess, self).__init__(network)

    def step(self, verbose=True):

        current_generation = int(math.floor((len(self.network.agents)*1.0-1)/self.network.agents_per_generation))

        if (len(self.network.agents) % self.network.agents_per_generation) == 1:
            self.environment.step()

        newcomer = self.network.last_agent

        if (current_generation == 0):
            self.network.sources[0].transmit(to_whom=newcomer)
            newcomer.receive_all()
        else:
            parent = None
            potential_parents = newcomer.predecessors2

            incoming_vectors = Vector.query.filter_by(destination=newcomer).all()
            potential_parents = [v.origin for v in incoming_vectors if isinstance(v.origin, Agent)]

            # potential_parents = self.network.agents_of_generation(current_generation-1)
            potential_parent_fitnesses = [p.fitness for p in potential_parents]
            potential_parent_probabilities = [(f/(1.0*sum(potential_parent_fitnesses))) for f in potential_parent_fitnesses]
            # print ["%.2f" % (p,) for p in potential_parent_probabilities]

            rnd = random.random()
            temp = 0.0
            for i, probability in enumerate(potential_parent_probabilities):
                temp += probability
                if temp > rnd:
                    parent = potential_parents[i]
                    break

            parent.transmit(what=Gene, to_whom=newcomer)
            newcomer.receive_all()

        if (newcomer.learning_gene.contents == "social"):
            rnd = random.randint(0, (self.network.agents_per_generation-1))
            cultural_parent = potential_parents[rnd]
            cultural_parent.transmit(what=Meme, to_whom=newcomer)
            newcomer.receive_all()
        elif (newcomer.learning_gene.contents == "asocial"):
            # Observe the environment.
            newcomer.observe(self.environment)
        else:
            raise AssertionError("Learner gene set to non-coherent value")


class RogersAgent(Agent):

    __mapper_args__ = {"polymorphic_identity": "rogers_agent"}

    @property
    def fitness(self):
        state = State\
            .query\
            .order_by(desc(Info.creation_time))\
            .first()

        matches_environment = (self.meme.contents == state.contents)
        is_asocial = (self.learning_gene.contents == "asocial")

        e = 2

        b = 20
        c = 9
        baseline = 10

        return (baseline + matches_environment * b - is_asocial * c) ** e

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

            if isinstance(info_in, MutationGene):
                self.replicate(info_in)

            elif isinstance(info_in, LearningGene):
                self.mutate(info_in)

            elif isinstance(info_in, Meme):
                self.replicate(info_in)

            elif isinstance(info_in, State):
                if random.random() < 1:
                    # Observe the environment cleanly.
                    info_out = Meme(origin=self, contents=info_in.contents)
                    SuccessfulObservation(
                        info_out=info_out,
                        info_in=info_in,
                        node=self)

                else:
                    # Flip the bit.
                    new_observation = str(info_in.contents != "True")
                    info_out = Meme(origin=self, contents=new_observation)
                    FailedObservation(
                        info_out=info_out,
                        info_in=info_in,
                        node=self)

            else:
                raise ValueError(
                    "{} can't update on {}s".format(self, type(info_in)))


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

    def __init__(self, session):

        self.session = session

        try:
            assert(len(State.query.all()))
        except Exception:
            state = State(
                origin=self,
                origin_uuid=self.uuid,
                contents=True)

            self.session.add(state)

    def step(self):

        if random.random() < 0.10:
            print "mutate!"
            current_state = (self.state.contents == "True")
            State(
                origin=self,
                origin_uuid=self.uuid,
                contents=str(not current_state))
