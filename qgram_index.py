"""
Copyright 2019, University of Freiburg
Chair of Algorithms and Data Structures.
Hannah Bast <bast@cs.uni-freiburg.de>
Claudius Korzen <korzen@cs.uni-freiburg.de>
Patrick Brosi <brosi@cs.uni-freiburg.de>
Natalie Prange <prange@cs.uni-freiburg.de>
"""

import itertools
import sys
import time

from typing import List, Tuple, Optional

# Uncomment to use C version of prefix edit distance calculation.
# from ped_c import ped

# Comment to use C version of prefix edit distance calculation
from ped_python import ped


class QGramIndex:
    """
    A QGram-Index.
    """

    def __init__(self, q: int, use_syns: Optional[bool] = False):
        """
        Creates an empty qgram index.
        """
        self.q = q
        self.padding = "$" * (self.q - 1)
        self.inverted_lists = {}
        self.entities = []
        self.norm_names = []
        self.names = []
        self.name_ent = []
        self.use_syns = use_syns

        # statistics
        self.ped_calcs = None
        self.ped_time = 0
        self.merges = None
        self.merge_time = 0

    def build_from_file(self, file_name: str):
        """
        Builds the index from the given file (one line per entity, see ES5).

        The entity IDs are one-based (starting with one).

        >>> q = QGramIndex(3, False)
        >>> q.build_from_file("test.tsv")
        >>> sorted(q.inverted_lists.items())
        ... # doctest: +NORMALIZE_WHITESPACE
        [('$$b', [(2, 1)]), ('$$f', [(1, 1)]), ('$br', [(2, 1)]),
         ('$fr', [(1, 1)]), ('bre', [(2, 1)]), ('fre', [(1, 1)]),
         ('rei', [(1, 1), (2, 1)])]
        """
        with open(file_name, "r", encoding="utf-8") as f:
            ent_id = 0
            name_id = 0
            f.readline()  # skip first line

            for line in f:
                ent_id += 1
                parts = line.split("\t")

                # cache the entity
                self.entities.append(parts)

                # all synonyms
                synonyms = []

                if self.use_syns:
                    if (len(parts) >= 6):
                        synonyms = parts[5].split(";")
                names = [parts[0]] + synonyms

                for n in names:
                    name_id += 1
                    self.name_ent.append(ent_id)
                    normed_name = self.normalize(n)
                    # cache the normalized names
                    self.norm_names.append(normed_name)
                    self.names.append(n)

                    for qgram in self.compute_qgrams(normed_name):
                        if qgram not in self.inverted_lists:
                            self.inverted_lists[qgram] = []
                        if (len(self.inverted_lists[qgram]) > 0 and
                                self.inverted_lists[qgram][-1][0] == name_id):
                            freq = self.inverted_lists[qgram][-1][1] + 1
                            self.inverted_lists[qgram][-1] = (name_id, freq)
                        else:
                            self.inverted_lists[qgram].append((name_id, 1))

    def compute_qgrams(self, word: str) -> List[str]:
        """
        Compute q-grams for padded version of given string.

        >>> q = QGramIndex(3, False)
        >>> q.compute_qgrams("freiburg")
        ['$$f', '$fr', 'fre', 'rei', 'eib', 'ibu', 'bur', 'urg']
        """
        ret = []
        padded = self.padding + word
        for i in range(0, len(word)):
            ret.append(padded[i:i + self.q])
        return ret

    def merge_lists(self, lists: List[List[Tuple[int, int]]]) \
            -> List[Tuple[int, int]]:
        """
        Merges the given inverted lists.

        >>> q = QGramIndex(3, False)
        >>> q.merge_lists([[(1, 2), (3, 1), (5, 1)], [(2, 1), (3, 2), (9, 2)]])
        [(1, 2), (2, 1), (3, 3), (5, 1), (9, 2)]
        >>> q.merge_lists([[(1, 2), (3, 1), (5, 1)], []])
        [(1, 2), (3, 1), (5, 1)]
        >>> q.merge_lists([[], []])
        []
        """
        start = time.monotonic()
        merged = []
        c = 0
        for el in sorted(itertools.chain.from_iterable(lists)):
            c += 1
            if len(merged) != 0 and merged[-1][0] == el[0]:
                merged[-1] = (merged[-1][0], merged[-1][1] + el[1])
            else:
                merged.append(el)

        self.merges = (len(lists), c)
        self.merge_time = (time.monotonic() - start) * 1000
        return merged

    def find_matches(self, prefix: str, delta: int) \
            -> Tuple[List[Tuple[int, int, int, int]], int]:
        """
        Finds all entities y with PED(x, y) <= delta for a given integer delta
        and a given (normalized) prefix x.

        The test checks for a tuple that contains (1) a list of triples
        containing the entity ID, the PED distance and its score and (2) the
        number of PED calculations

        ([(entity id, PED, score), ...], #ped calculations)

        The entity IDs are one-based (starting with 1).

        >>> q = QGramIndex(3, False)
        >>> q.build_from_file("test.tsv")
        >>> q.find_matches("frei", 0)
        ([(1, 0, 3, 1)], 1)
        >>> q.find_matches("frei", 2)
        ([(1, 0, 3, 1), (2, 1, 2, 2)], 2)
        >>> q.find_matches("freibu", 2)
        ([(1, 2, 3, 1)], 2)
        """
        threshold = len(prefix) - (self.q * delta)
        matches = []
        tot = 0
        c = 0

        lists = []
        for qgram in self.compute_qgrams(prefix):
            if qgram in self.inverted_lists:
                lists.append(self.inverted_lists[qgram])

        merged = self.merge_lists(lists)

        start = time.monotonic()

        for pair in merged:
            tot += 1
            if pair[1] >= threshold:
                # ids are 1-based
                pedist = ped(prefix, self.norm_names[pair[0] - 1], delta)
                c += 1
                if pedist <= delta:
                    matches.append(
                        (self.name_ent[pair[0] - 1], pedist, pair[0]))
                    continue

        self.ped_calcs = (c, tot)
        self.ped_time = (time.monotonic() - start) * 1000

        # only one result per entity, namely the best PED
        matches = sorted(matches, key=lambda match: (match[0], match[1]))

        ret = []

        for match in matches:
            if len(ret) == 0 or ret[-1][0] != match[0]:
                ret.append((match[0], match[1], int(
                    self.entities[match[0] - 1][1]), match[2]))

        return ret, c

    def normalize(self, word: str) -> str:
        """
        Normalize the given string (remove non-word characters and lower case).

        >>> q = QGramIndex(3, False)
        >>> q.normalize("freiburg")
        'freiburg'
        >>> q.normalize("Frei, burG !?!")
        'freiburg'
        """
        low = word.lower()
        return ''.join([i for i in low if i.isalnum()])

    def rank_matches(self, matches: List[Tuple[int, int, int, int]]) \
            -> List[Tuple[int, int, int, int]]:
        """
        Ranks the given list of (entity id, PED, s), where PED is the PED
        value and s is the popularity score of an entity.

        The test check for a list of triples containing the entity ID,
        the PED distance and its score:

        [(entity id, PED, score), ...]

        >>> q = QGramIndex(3, False)
        >>> q.rank_matches([(1, 0, 3), (2, 1, 2), (2, 1, 3), (1, 0, 2)])
        [(1, 0, 3), (1, 0, 2), (2, 1, 3), (2, 1, 2)]
        """
        return sorted(matches, key=lambda post: (post[1], -post[2]))


def main():
    """
    Builds a qgram index from the given file and then, in an infinite loop,
    lets the user type a query and shows the result for the normalized query.
    """
    # Parse the command line arguments.
    if len(sys.argv) < 2:
        print(f"Usage: python3 {sys.argv[0]} <file> [--use-synonyms]")
        sys.exit()

    file_name = sys.argv[1]

    use_synonyms = len(sys.argv) > 2

    # Create a new index from the given file.
    print(f"Reading from file '{file_name}'.")
    start = time.monotonic()
    q = QGramIndex(3, use_synonyms)
    q.build_from_file(file_name)
    print(f"Done, took {(time.monotonic() - start) * 1000} ms.")

    while True:
        # Ask the user for a keyword query.
        query = input("\nYour keyword query: ")
        query = q.normalize(query)

        start = time.monotonic()

        # Process the keywords.
        delta = int(len(query) / 4)

        postings, _ = q.find_matches(query, delta)
        print(
            f"Got {len(postings)} result(s), merged {q.merges[0]} lists with "
            f"tot. {q.merges[1]} elements ({q.merge_time} ms), "
            f"{q.ped_calcs[0]}/{q.ped_calcs[1]} ped calculations ({q.ped_time}"
            f" ms), took \033[1m{(time.monotonic() - start) * 1000} ms\033[0m"
            f" total.")

        for ent in q.rank_matches(postings)[:5]:
            print(f"\n\033[1m{q.entities[ent[0] - 1][0]}\033[0m (score="
                  f"{ent[2]}, ped={ent[1]}, via '{q.names[ent[3] - 1]}'):\n"
                  f"{q.entities[ent[0] - 1][2]}")


if __name__ == "__main__":
    main()
