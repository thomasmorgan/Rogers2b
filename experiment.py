from wallace.processes import Process
from wallace.recruiters import PsiTurkRecruiter
from wallace.agents import ReplicatorAgent, Agent
from wallace.experiments import Experiment
from wallace.sources import Source
from wallace.information import Gene, Meme
from wallace.models import Info
from wallace.networks import Network
import math
import random
from sqlalchemy import desc


class LearningGene(Gene):
    __mapper_args__ = {"polymorphic_identity": "learning_gene"}


class MutationGene(Gene):
    __mapper_args__ = {"polymorphic_identity": "mutation_gene"}


class Rogers(Experiment):
    def __init__(self, session):
        super(Rogers, self).__init__(session)

        self.task = "Rogers network game"
        self.num_agents_per_generation = 3
        self.num_generations = 3
        self.num_agents = self.num_agents_per_generation*self.num_generations
        self.agent_type = RogersAgent
        self.network = RogersNetwork(self.agent_type, self.session, self.num_agents_per_generation, self.num_generations)
        self.process = RogersNetworkProcess(self.network)
        self.recruiter = PsiTurkRecruiter

        # Setup for first time experiment is accessed
        if not self.network.sources:
            source = RogersSource()
            self.network.add_source_global(source)

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
        self.network.db.commit()

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


    def _selector(self):
        info = Gene(
            origin=self,
            origin_uuid=self.uuid,
            contents=self._data())

        return [info]


class RogersNetwork(Network):
    """In a Rogers Network agents are arranged into genenerations of a set size
    and each agent is connected to all agents in the previous generation (the
    first generation agents are connected to a source)
    """

    def __init__(self, agent_type, db, agents_per_generation=10, num_generations=10):
        self.db = db
        self.agents_per_generation = agents_per_generation
        self.num_generations = num_generations
        super(RogersNetwork, self).__init__(agent_type, db)

    @property
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
            self.db.commit()

        self.db.add(newcomer)
        self.db.commit()

        # Place them in the network.
        if len(self.agents) <= self.agents_per_generation:
            self.sources[0].connect_to(newcomer)
            self.db.commit()
        else:
            newcomer_generation = math.floor(((len(self.agents)-1)*1.0)/self.agents_per_generation)
            min_previous_generation = (newcomer_generation-1)*self.agents_per_generation
            previous_generation_agents = self.db.query(Agent)\
                .filter(Agent.status != "failed")\
                .order_by(Agent.creation_time)[min_previous_generation:(min_previous_generation+self.agents_per_generation)]

            for a in previous_generation_agents:
                a.connect_to(newcomer)
            self.db.commit()

        return newcomer

    def agents_of_generation(self, generation):
        first_index = generation*self.agents_per_generation
        last_index = first_index+(self.agents_per_generation)
        return self.agents[first_index:last_index]


class RogersNetworkProcess(Process):

    def __init__(self, network):
        self.network = network
        super(RogersNetworkProcess, self).__init__(network)

    def step(self, verbose=True):

        newcomer = self.network.last_agent
        current_generation = int(math.floor((len(self.network.agents)*1.0-1)/self.network.agents_per_generation))

        if (current_generation == 0):
            self.network.sources[0].transmit(self.network.agents[len(self.network.agents)-1], selector=Gene)
            newcomer.receive_all()
        else:
            parent = None
            potential_parents = self.network.agents_of_generation(current_generation-1)
            potential_parent_fitnesses = [p.fitness() for p in potential_parents]
            potential_parent_probabilities = [(f/(1.0*sum(potential_parent_fitnesses))) for f in potential_parent_fitnesses]
            rnd = random.random()
            temp = 0.0
            for i, probability in enumerate(potential_parent_probabilities):
                temp += probability
                if rnd < temp:
                    parent = potential_parents[i]
            parent.transmit(newcomer, selector=Gene)
            newcomer.receive_all()

            if (newcomer.gene.contents == "social"):
                rnd = random.randint(0, (self.network.agents_per_generation-1))
                cultural_parent = potential_parents[rnd]
                cultural_parent.transmit(newcomer, selector=Meme)
                newcomer.receive_all()
            elif (newcomer.gene.contents == "asocial"):
                pass
            else:
                raise AssertionError("Learner gene set to non-coherent value")


class RogersAgent(Agent):

    __mapper_args__ = {"polymorphic_identity": "rogers_agent"}

    def fitness(self):
        return 1

    @property
    def mutation_rate(self):
        gene = MutationGene.query.first()
        return gene.contents

    @property
    def gene(self):
        gene = Gene\
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

    def update(self, info):

        info.copy_to(self)

        # Mutate.
        if random.random() < self.mutation_rate:
            all_strategies = ["social", "asocial"]
            self.gene.contents = all_strategies[not all_strategies.index(self.gene.contents)]
