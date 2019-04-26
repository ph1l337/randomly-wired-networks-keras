import tensorflow as tf
from tensorflow.python import keras, TensorShape
import networkx as nx


class Node(keras.layers.Layer):
    def __init__(self, channels, kernel_size, **kwargs):
        self.channels = channels
        self.kernel_size = kernel_size
        super(Node, self).__init__(**kwargs)

    def build(self, input_shape):
        if type(input_shape) is not list:
            raise TypeError("A node needs to be called with a list of "
                            "tensors (even if it only has one parent node)")
        if not all([shape == input_shape[0] for shape in input_shape]):
            raise ValueError("All inputs must have the same shape. Found {}".format(input_shape))

        self.aggregate_w = self.add_weight(
            name='{}_aggregate_w'.format(self.name),
            shape=len(input_shape),
            initializer=keras.initializers.zeros,
            trainable=True
        )

        self.conv = keras.layers.SeparableConv2D(
            name='{}_conv'.format(self.name),
            filters=self.channels,
            kernel_size=self.kernel_size,
            padding='same'
        )

        self.batch_norm = keras.layers.BatchNormalization(
            name='{}_batch_norm'.format(self.name)
        )
        super(Node, self).build(input_shape)

    def call(self, inputs, **kwargs):
        x = tf.stack(inputs)
        # Todo: the way I understand the paper even if there is only one input there is a corresponding weight
        x = tf.tensordot(x, keras.backend.sigmoid(self.aggregate_w), [[0], [0]])

        x = keras.activations.relu(x)
        x = self.conv(x)
        x = self.batch_norm(x)
        return x

    def compute_output_shape(self, input_shape):
        return TensorShape((input_shape[0][0], input_shape[0][1], input_shape[0][2], self.channels))

    def get_config(self):
        base_config = super(Node, self).get_config()
        base_config['channels'] = self.channels
        base_config['kernel_size'] = self.kernel_size
        return base_config

    @classmethod
    def from_config(cls, config):
        return cls(**config)


class RandomWiring(keras.layers.Layer):
    def __init__(self,
                 channels,
                 stride,
                 random_graph_model,
                 kernel_size=(3,3),
                 n=32,
                 k=4,
                 p=0.75,
                 m=5,
                 seed=0,
                 **kwargs):
        self.channels = channels
        self.stride = stride
        self.random_graph_model = random_graph_model
        self.kernel_size = kernel_size
        self.n = n
        self.k = k
        self.p = p
        self.seed = seed

        if random_graph_model == "ws":
            random_graph = nx.connected_watts_strogatz_graph(n, k, p, seed=seed)
        elif random_graph_model == "ba":
            random_graph = nx.barabasi_albert_graph(n, m, seed=seed)
        elif random_graph_model == 'er':
            random_graph = nx.erdos_renyi_graph(n, p, seed=seed)
        else:
            raise ValueError('random_graph_model must be either "ws", "ba" or "er"')

        self.dag = nx.DiGraph()
        self.dag.add_edges_from(random_graph.edges)

        self.dag_output_nodes = [node for node in self.dag.nodes if self.dag.out_degree[node] == 0]

        assert nx.is_directed_acyclic_graph(self.dag)

        super(RandomWiring, self).__init__(**kwargs)

    def build(self, input_shape):
        self.input_node = Node(channels=self.channels, kernel_size=self.kernel_size)
        self.nodes = [Node(channels=self.channels, kernel_size=self.kernel_size) for _ in range(self.n)]
        self.output_node = Node(channels=self.channels, kernel_size=self.kernel_size)

    def call(self, inputs, **kwargs):
        node_outputs = [None for _ in range(self.n)]

        x = self.input_node([inputs])
        for node in nx.topological_sort(self.dag):
            if self.dag.in_degree[node] == 0:
                node_outputs[node] = self.nodes[node]([x])
                continue

            predecessor_outputs = []
            for predecessor in self.dag.predecessors(node):
                predecessor_outputs.append(node_outputs[predecessor])

            node_outputs[node] = self.nodes[node](predecessor_outputs)

        dag_outputs = []
        for dag_output_node in self.dag_output_nodes:
            dag_outputs.append(node_outputs[dag_output_node])

        x = self.output_node(dag_outputs)
        return x

    def compute_output_shape(self, input_shape):
        return TensorShape((input_shape[0][0], input_shape[0][1], input_shape[0][2], self.channels))

    def get_config(self):
        base_config = super(RandomWiring, self).get_config()
        base_config['channels'] = self.channels
        base_config['stride'] = self.stride
        base_config['kernel_size'] = self.kernel_size
        base_config['random_graph_model'] = self.random_graph_model
        base_config['n'] = self.n
        base_config['k'] = self.k
        base_config['p'] = self.p
        base_config['seed'] = self.seed
        return base_config

    @classmethod
    def from_config(cls, config):
        return cls(**config)
