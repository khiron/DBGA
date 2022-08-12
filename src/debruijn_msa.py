from __future__ import annotations
from pathlib import Path
from typing import Any, Dict, List, Tuple, Set, Union
from utils import *

from cogent3 import SequenceCollection


class deBruijnMultiSeqs:
    """The de Bruijn graph class, with construction, visualization and alignment

    Attributes
    ----------
    id_count : int
        the current id of nodes added to the de Bruijn graph
    k : int
        the kmer size of the de Bruijn graph
    nodes : Dict[int, Node]
        the map from NodeID to Node object
    exist_kmer : Dict[str, int]
        currently existing kmer in de Bruijn graph, stored in form of (kmer: NodeID)
    seq_node_idx : Dict[int, List[int]]
        the map from sequence ID to the list of Node indices from that sequence
    merge_node_idx : List[int]
        the list of Node indices of shared kmers
    merge_node_idx_temp : List[int]
        the temporary list for storing Node indices of shared kmers before calculating intersection
    seq_last_kmer_id : List[int]
        the NodeID for last kmer in each sequence
    moltype : str
        the molecular type for characters in sequences
    names : Tuple[Any, ...]
        the sequences names
    sequences : Tuple[str, ...]
        the sequences contained in the de Bruijn graph
    num_seq : int
        number of sequences in the de Bruijn graph
    avg_len : int
        average length of sequences

    """

    def __init__(self, data: Any, k: int, moltype: str) -> None:
        """Constructor for a de Bruijn graph

        Parameters
        ----------
        data : Any
            can be path to sequences or List of sequences or SequenceCollection object
        k : int
            the kmer size for the de Bruijn graph

        Returns
        -------

        """
        sc: SequenceCollection = load_sequences(data=data, moltype=moltype)
        self.id_count = 0
        self.k = k
        self.nodes: Dict[int, Node] = {}
        self.exist_kmer: Dict[str, int] = {}
        self.seq_node_idx: Dict[int, List[int]] = {}
        self.merge_node_idx: List[int] = []
        self.merge_node_idx_temp: List[int] = []
        self.seq_last_kmer_idx: List[int] = []
        self.moltype: str = moltype
        self.names: Tuple[Any, ...] = tuple(sc.names)
        self.sequences: Tuple[str, ...] = tuple([str(seq) for seq in sc.seqs])
        self.num_seq: int = len(self.sequences)
        # calculate the average sequences length
        self.avg_len = sum(map(len, self.sequences)) / self.num_seq
        self.add_debruijn()
        self.expansion = self.extract_bubble()

    def _add_node(self, kmer: str = "", node_type: NodeType = NodeType.middle) -> int:
        """Add a single node to the de Bruijn graph

        Parameters
        ----------
        kmer : str, optional
            the kmer from the sequence. Defaults to ""
        node_type : NodeType, optional
            the NodeType of the new node added. Defaults to NodeType.middle

        Returns
        -------
        int
            the node id of the provided kmer

        """
        if kmer in self.exist_kmer:
            exist_node_id = self.exist_kmer[kmer]
            self.nodes[exist_node_id].count += 1
            self.merge_node_idx_temp.append(exist_node_id)
            return exist_node_id

        new_node = Node(id=self.id_count, kmer=kmer, node_type=node_type)
        self.nodes[self.id_count] = new_node

        if node_type is NodeType.middle:
            self.exist_kmer[kmer] = self.id_count

        self.id_count += 1
        return self.id_count - 1

    def _add_edge(
        self,
        out_id: int,
        in_id: int,
        seq_idx: int,
        duplicate_str: str = "",
        multiple_duplicate: bool = False,
    ) -> None:
        """Connect two kmers in the de Bruijn graph with an edge

        Parameters
        ----------
        out_id : int
            the starting node id
        in_id : int
            the terminal node id
        seq_idx : int
            the sequence index of the current kmer connection
        duplicated_str : str, Optional
            the duplicated kmer represented by the edge
        multiple_duplicate : bool, Optional
            indicate whether the duplicate_str contain multiple kmers


        Returns
        -------

        """
        self.nodes[out_id].add_out_edge(
            in_id, seq_idx, duplicate_str, multiple_duplicate
        )

    def _get_seq_kmer_indices(
        self, kmers: List[str], duplicate_kmer: Set[str], seq_idx: int
    ) -> List[int]:
        """Add kmers (of a sequence) to the de Bruijn graph, also get their indices

        Parameters
        ----------
        kmers : List[str]
            kmers of a sequence
        duplicate_kmer : Set[str]
            kmers where they are recorded to be duplicate (not included in nodes)

        Returns
        -------
        List[int]
            the indices of nodes where kmers are added

        """
        # to record the duplicated kmers
        edge_kmer = []
        # starting node
        prev_idx = self._add_node(kmer="", node_type=NodeType.start)
        node_indices = [prev_idx]
        multiple_duplicate = False
        for kmer in kmers:
            if kmer in duplicate_kmer:
                if edge_kmer:
                    multiple_duplicate = True
                edge_kmer.append(kmer)
                current_idx = prev_idx
            elif len(edge_kmer) > 0:
                # if there are duplicated kmers, store them in the edge
                current_idx = self._add_node(kmer)
                node_indices.append(current_idx)
                self._add_edge(
                    prev_idx,
                    current_idx,
                    seq_idx,
                    "".join(edge_kmer),
                    multiple_duplicate,
                )
                edge_kmer = []
            else:
                # if there is no duplicated kmer, add new nodes
                current_idx = self._add_node(kmer)
                node_indices.append(current_idx)
                self._add_edge(prev_idx, current_idx, seq_idx)

            # store the previous node index
            prev_idx = current_idx

        if not edge_kmer:
            self.seq_last_kmer_idx.append(current_idx)
        else:
            # if -1, the last kmer is shown as edge, should be read fully
            self.seq_last_kmer_idx.append(-1)
        # create the terminal node and connect with the previous node
        end_node = self._add_node(kmer="", node_type=NodeType.end)
        node_indices.append(end_node)
        self._add_edge(
            current_idx, end_node, seq_idx, "".join(edge_kmer), multiple_duplicate
        )

        # return the sequence kmer indices
        if not self.merge_node_idx:
            self.merge_node_idx = self.merge_node_idx_temp
        else:
            self.merge_node_idx = list_intersection(
                self.merge_node_idx, self.merge_node_idx_temp
            )
        # empty the temporary list
        self.merge_node_idx_temp = []

        return node_indices

    def add_debruijn(self) -> None:
        """Construct de Bruijn graph for the given sequences

        Parameters
        ----------

        Returns
        -------

        """
        # get kmers
        kmer_seqs = [get_kmers(seq, self.k) for seq in self.sequences]
        # find the duplicate kmers in each sequence
        duplicate_kmer = duplicate_kmers(kmer_seqs=kmer_seqs)
        # add nodes to de Bruijn graph
        for i, kmer_seq in enumerate(kmer_seqs):
            self.seq_node_idx[i] = self._get_seq_kmer_indices(
                kmers=kmer_seq, duplicate_kmer=duplicate_kmer, seq_idx=i
            )

    def visualize(self, path: str, save_dot: bool = False) -> None:  # pragma: no cover
        """Visualize the de Bruijn graph

        Parameters
        ----------
        path : str
            the path to the output image file
        save_dot : bool, optional
            whether save the DOT representation to file. Defaults to False.

        Returns
        -------

        Raises
        ------
        ValueError
            when the image file extension is not recognized

        """
        file_path = Path(path).expanduser().absolute()
        suffix = file_path.suffix[1:]
        if suffix not in ["pdf", "png", "svg"]:
            raise ValueError("Not supported file format")
        digraph = to_DOT(list(self.nodes.values()))
        # output the image
        digraph.render(outfile=file_path, format=suffix, cleanup=True)
        if save_dot:
            dot_file_path = file_path.with_suffix(".DOT")
            digraph.save(dot_file_path)

    def read_from_kmer(self, node_idx: int, seq_idx: int) -> str:
        """Read nucleotide(s) from the kmer with provided index

        Parameters
        ----------
        node_idx : int
            the node index of the kmer to read
        seq_idx : int
            the sequence index from kmer

        Returns
        -------
        str
            the nucleotide(s) read from the kmer

        """
        kmer = self.nodes[node_idx].kmer
        return kmer if node_idx == self.seq_last_kmer_idx[seq_idx] else kmer[0]

    def extract_bubble(self) -> List[List[Union[int, List[int]]]]:
        """Extract indicies of bubbles and merge nodes of sequences in the de Bruijn graph

        Returns
        -------
        List[List[Union[int, List[int]]]]
            List of indicies of bubbles and merge nodes of sequences in the de Bruijn graph
        """
        # FIXME: Need a new method for extract bubble. Future MSA alignment is based on this method
        expansion = []
        for seq_idx in range(self.num_seq):
            bubbles = []
            bubble = []
            for node_idx in self.seq_node_idx[seq_idx]:
                # if self.nodes[node_idx].node_type not in {NodeType.start, NodeType.end}:
                # Add empty lists to the expansion even if there's no bubble
                if node_idx not in self.merge_node_idx:
                    bubble.append(node_idx)
                else:
                    bubbles.append(bubble)
                    bubble = []
                    bubbles.append(node_idx)
            bubbles.append(bubble)
            expansion.append(bubbles)
        return expansion

    def extract_bubble_seq(self, bubble_idx_seq: List[int], seq_idx: int) -> str:
        """Extract the string from the bubble with indices of nodes

        Parameters
        ----------
        bubble_idx_seq : List[int]
            indices of nodes that are in the bubble
        seq_idx : int
            the sequence index the bubble belongs to

        Returns
        -------
        str
            the string from the bubble with indices of nodes

        """
        # the last index will always representing the merge node or the end node (last bubble)
        rtn = []
        for i in range(len(bubble_idx_seq) - 1):
            node_idx = bubble_idx_seq[i]
            if self.nodes[node_idx].node_type not in [NodeType.start, NodeType.end]:
                rtn.append(self.read_from_kmer(node_idx, seq_idx))
            next_node_idx = bubble_idx_seq[i + 1]
            # if the next node is the end of sequence, read edge fully,
            # otherwise, read the first char
            out_edge = self.nodes[node_idx].out_edges[seq_idx]
            edge_kmer = out_edge.duplicate_str
            if self.nodes[next_node_idx].node_type is NodeType.end:
                if out_edge.multiple_duplicate:
                    rtn.append(read_nucleotide_from_kmers(edge_kmer[: -self.k], self.k))
                    rtn.append(edge_kmer[-self.k :])
                else:
                    rtn.append(edge_kmer)
            else:
                rtn.append(read_nucleotide_from_kmers(edge_kmer, self.k))

        # if the next node is not end node, then it should be a merge node
        # last_node_idx = bubble_idx_seq[-1]
        # if not self.nodes[last_node_idx].node_type is NodeType.end:
        #     rtn.append(self.read_from_kmer(last_node_idx, seq_idx=seq_idx))
        return "".join(rtn)

    def bubble_aln(
        self,
        bubble_indices_seq1: List[int],
        bubble_indices_seq2: List[int],
        s: Dict[Tuple[str, str], int],
        d: int,
        e: int,
        prev_edge_read1: str = "",
        prev_edge_read2: str = "",
        prev_merge: str = "",
    ) -> Tuple[str, str]:
        """Align the bubbles in the de Bruijn graph

        Parameters
        ----------
        bubble_idx_seq1 : List[int]
            the list containing indices of nodes of seq1 in the bubble
        bubble_idx_seq2 : List[int]
            the list containing indices of nodes of seq2 in the bubble
        s : Dict[Tuple[str, str], int]
            the DNA scoring matrix
        d : int
            gap open costs
        e : int
            gap extend costs
        prev_edge_read1 : str, optional
            the edge kmer from the edge of the last merge node for seq1. Defaults to "".
        prev_edge_read2 : str, optional
            the edge kmer from the edge of the last merge node for seq2. Defaults to "".
        prev_merge : str, optional
            the previous merge node nucleotide. Defaults to "".

        Returns
        -------
        Tuple[str, str]
            the aligned sequences from the bubble in the de Bruijn graph

        """
        # short cut for faster experiments
        if (
            len(bubble_indices_seq1) == len(bubble_indices_seq2) == 1
            and prev_edge_read1 == prev_edge_read2 == ""
        ):
            return prev_merge, prev_merge

        # extract original bubble sequences
        bubble_seq1_str = f"{prev_merge}{prev_edge_read1}{self.extract_bubble_seq(bubble_indices_seq1, 0)}"
        bubble_seq2_str = f"{prev_merge}{prev_edge_read2}{self.extract_bubble_seq(bubble_indices_seq2, 1)}"

        # call the global_aln function to compute the global alignment of two sequences
        return dna_global_aln(bubble_seq1_str, bubble_seq2_str, s=s, d=d, e=e)

    def get_merge_edge(
        self,
        seq1_curr_idx: int,
        seq2_curr_idx: int,
    ) -> Tuple[str, str]:
        """To get the duplicate_kmer from the edge that is from the merge node

        Parameters
        ----------
        seq1_curr_idx : int
            current node index of sequence1
        seq2_curr_idx : int
            current node index of sequence2

        Returns
        -------
        Tuple[str, str]
            the duplicate_kmer string for each sequence that is from the merge node

        """
        seq1_edge_kmer = self.nodes[seq1_curr_idx].out_edges[0].duplicate_str
        seq2_edge_kmer = self.nodes[seq2_curr_idx].out_edges[1].duplicate_str
        # no chance that next node is End NodeType, we won't call this function for the last merge node
        merge_edge_read_seq1 = read_nucleotide_from_kmers(seq1_edge_kmer, self.k)
        merge_edge_read_seq2 = read_nucleotide_from_kmers(seq2_edge_kmer, self.k)
        return merge_edge_read_seq1, merge_edge_read_seq2
