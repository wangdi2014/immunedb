import distance
import re
import numpy as np

from Bio.Seq import Seq

import sldb.identification.anchors as anchors
import sldb.identification.germlines as germlines
from sldb.util.funcs import find_streak_position
from sldb.identification.v_genes import VGene, get_common_seq


class VDJSequence(object):
    MISMATCH_THRESHOLD = 3
    MIN_J_ANCHOR_LEN = 12
    INDEL_WINDOW = 30
    INDEL_MISMATCH_THRESHOLD = .6

    def __init__(self, id, seq, is_full_v, v_germlines, force_vs=None,
                 force_j=None):
        self._id = id
        self._seq = seq
        self._is_full_v = is_full_v
        self.v_germlines = v_germlines

        self._seq_filled = None

        self._j = force_j
        self._j_anchor_pos = None
        self._j_match = None

        self._v = force_vs
        self._v_anchor_pos = None
        self._v_match = None

        self._mutation_frac = None
        self._germline = None
        self._cdr3_len = 0

        self._possible_indel = False

        self.copy_number = 1

        # If there are invalid characters in the sequence, ignore it
        stripped = filter(lambda s: s in 'ATCGN', self.sequence)
        if len(stripped) == len(self.sequence):
            self._find_j()
            if self._j is not None:
                self._get_v(reverse=False)

    @property
    def id(self):
        return self._id

    @property
    def j_gene(self):
        if self._j is None:
            return None
        return sorted(self._j)

    @property
    def v_gene(self):
        if self._v is None:
            return None
        return sorted(self._v)

    @v_gene.setter
    def v_gene(self, v):
        self._v = v

    @property
    def j_anchor_pos(self):
        return self._j_anchor_pos

    @property
    def v_anchor_pos(self):
        return self._v_anchor_pos

    @property
    def cdr3(self):
        return self.sequence[VGene.CDR3_OFFSET:
                             VGene.CDR3_OFFSET + self._cdr3_len]

    @property
    def sequence(self):
        return self._seq

    @property
    def sequence_filled(self):
        if self._seq_filled is None:
            self._seq_filled = ''
            for i, c in enumerate(self.sequence):
                if c.upper() == 'N':
                    self._seq_filled += self.germline[i].upper()
                else:
                    self._seq_filled += c
        return self._seq_filled

    @property
    def aligned_v(self):
        return self._aligned_v

    @property
    def germline(self):
        return self._germline

    @property
    def mutation_fraction(self):
        return self._mutation_frac

    @property
    def num_gaps(self):
        return self._num_gaps

    @property
    def pad_length(self):
        return self._pad_len if self._pad_len >= 0 else 0

    @property
    def in_frame(self):
        return len(self.cdr3) % 3 == 0

    @property
    def stop(self):
        for i in range(0, len(self.sequence), 3):
            if self.sequence[i:i+3] in ['TAG', 'TAA', 'TGA']:
                return True
        return False

    @property
    def functional(self):
        return self.in_frame and not self.stop

    @property
    def j_length(self):
        return self._j_length

    @property
    def j_match(self):
        return self._j_match

    @property
    def v_length(self):
        return self._v_length

    @property
    def v_match(self):
        return self._v_match

    @property
    def pre_cdr3_length(self):
        return self._pre_cdr3_length

    @property
    def pre_cdr3_match(self):
        return self._pre_cdr3_match

    @property
    def post_cdr3_length(self):
        return self._post_cdr3_length

    @property
    def post_cdr3_match(self):
        return self._post_cdr3_match

    def _find_j(self):
        '''Finds the location and type of J gene'''
        # Iterate over every possible J anchor.  For each germline, try its
        # full sequence, then exclude the final 3 characters at a time until
        # there are only MIN_J_ANCHOR_LEN nucleotides remaining.
        #
        # For example, the order for one germline:
        # TGGTCACCGTCTCCTCAG
        # TGGTCACCGTCTCCT
        # TGGTCACCGTCT

        # If forcing a J, set the dictionary, otherwise try all
        if self._j is not None:
            j_anchors = {self._j: anchors.j_anchors[self._j]}
        else:
            j_anchors = anchors.j_anchors

        for match, full_anchor, j_gene in anchors.all_j_anchors(
                self.MIN_J_ANCHOR_LEN, anchors=j_anchors):
            i = self._seq.rfind(match)
            if i >= 0:
                return self._found_j(i, j_gene, match, full_anchor)

            i = self._seq.reverse_complement().rfind(match)
            if i >= 0:
                # If found in the reverse complement, flip and translate the
                # actual sequence for the rest of the analysis
                self._seq = self._seq.reverse_complement()
                return self._found_j(i, j_gene, match, full_anchor)
        self._j = None

    def _found_j(self, i, j_gene, match, full_anchor):
        # If a match is found, record its location and gene
        self._j_anchor_pos = i
        self._j = [j_gene]

        # Get the full germline J gene
        j_full = germlines.j[self.j_gene[0]]
        # Get the portion of J in the CDR3
        j_in_cdr3 = j_full[:len(j_full) - germlines.j_offset]
        cdr3_end = (self._j_anchor_pos) - germlines.j_offset +\
            len(match)
        cdr3_segment = self.sequence[cdr3_end - len(j_in_cdr3):cdr3_end]
        if len(j_in_cdr3) == 0 or len(cdr3_segment) == 0:
            self._j = None
            return

        # Get the extent of the J in the CDR3
        streak = find_streak_position(
            reversed(j_in_cdr3),
            reversed(cdr3_segment),
            self.MISMATCH_THRESHOLD)
        # Trim the J gene based on the extent in the CDR3
        if streak is not None:
            j_full = j_full[streak:]

        # Find where the full J starts
        self._j_start = self._j_anchor_pos + len(match) - len(j_full)

        # If the trimmed germline J extends past the end of the
        # sequence, there is a misalignment
        if len(j_full) != len(
                self.sequence[self._j_start:self._j_start+len(j_full)]):
            self._j = None
            self._j_anchor_pos = None
            return

        # Get the full-J distance
        dist = distance.hamming(
            j_full,
            self.sequence[self._j_start:self._j_start+len(j_full)])

        self._j = anchors.get_j_ties(self.j_gene[0], match)
        self._j_length = len(j_full)
        self._j_match = self._j_length - dist

    def _get_v(self, reverse):
        self._v_anchor_pos = anchors.find_v_position(self.sequence, reverse)
        if self.v_anchor_pos is not None:
            self._find_v()
            if self.v_gene is None and not reverse:
                self._get_v(True)

    def _find_v(self):
        '''Finds the V gene closest to that of the sequence'''
        self._v_score = None
        self._aligned_v = VGene(self.sequence)
        if self._v:
            germlines = {vg: self.v_germlines[vg] for vg in self._v}
        else:
            germlines = self.v_germlines

        for v, germ in sorted(germlines.iteritems()):
            try:
                dist, total_length = germ.compare(self._aligned_v,
                                                  self._j_anchor_pos,
                                                  self.MISMATCH_THRESHOLD)
            except:
                continue
            # Record this germline if it is has the lowest distance
            if dist is not None:
                if self._v_score is None or dist < self._v_score:
                    self._v = [v]
                    self._v_score = dist
                    self._v_length = total_length
                    self._v_match = total_length - dist
                    self._germ_pos = germ.ungapped_anchor_pos
                elif dist == self._v_score:
                    # Add the V-tie
                    self._v.append(v)

        if self._v is None:
            return

        # Determine the pad length
        self._pad_len = self._germ_pos - self.v_anchor_pos
        # Mutation ratio is the distance divided by the length of overlap
        self._mutation_frac = self._v_score / float(self._v_length)

        # If we need to pad with a full sequence, there is a misalignment
        if self._is_full_v and self._pad_len > 0:
            self._v = None
            return

    def align_to_germline(self, avg_len, avg_mut):
        self._v = self.v_germlines.get_ties(self.v_gene, avg_len, avg_mut)
        # Set the germline to the V gene up to the CDR3
        self._germline = get_common_seq(
            [self.v_germlines[v].sequence for v in self._v]
        )[:VGene.CDR3_OFFSET]
        self._pad_len = (len(self._germline.replace('-', ''))
                         - self.v_anchor_pos)
        # If we need to pad the sequence, do so, otherwise trim the sequence to
        # the germline length
        if self._pad_len >= 0:
            self._seq = 'N' * self._pad_len + str(self._seq)
        else:
            self._seq = str(self._seq[-self._pad_len:])
        # Update the anchor positions after adding padding / trimming
        self._j_anchor_pos += self._pad_len
        self._v_anchor_pos += self._pad_len

        # Add germline gaps to sequence before CDR3 and update anchor positions
        for i, c in enumerate(self._germline):
            if c == '-':
                self._seq = self._seq[:i] + '-' + self._seq[i:]
                self._j_anchor_pos += 1
                self._v_anchor_pos += 1

        j_germ = germlines.j[self.j_gene[0]]
        # Find the J anchor in the germline J gene
        j_anchor_in_germline = j_germ.rfind(
            str(anchors.j_anchors[self.j_gene[0]]))
        # Calculate the length of the CDR3
        self._cdr3_len = (
            (self.j_anchor_pos + len(anchors.j_anchors[self.j_gene[0]])
                - germlines.j_offset) - self.v_anchor_pos)

        if self._cdr3_len <= 0:
            self._v = None
            return

        self._j_anchor_pos += self._cdr3_len
        # Fill germline CDR3 with gaps
        self._germline += '-' * self._cdr3_len
        self._germline += j_germ[-germlines.j_offset:]
        # If the sequence is longer than the germline, trim it
        if len(self.sequence) > len(self.germline):
            self._seq = self._seq[:len(self._germline)]
        elif len(self.sequence) < len(self.germline):
            # If the germline is longer than the sequence, there was probably a
            # deletion, so flag it as such
            self._seq += 'N' * (len(self.germline) - len(self.sequence))
            self._possible_indel = True

        # Get the number of gaps
        self._num_gaps = self.sequence[:VGene.CDR3_OFFSET].count('-')

        # Get the pre-CDR3 germline and sequence stripped of gaps
        pre_cdr3_germ = self.germline[:VGene.CDR3_OFFSET].replace('-', '')
        pre_cdr3_seq = self.sequence[:VGene.CDR3_OFFSET].replace('-', '')
        # If there is padding, get rid of it in the sequence and align the
        # germline
        if self._pad_len > 0:
            pre_cdr3_germ = pre_cdr3_germ[self._pad_len:]
            pre_cdr3_seq = pre_cdr3_seq[self._pad_len:]

        # Calculate the pre-CDR3 length and distance
        self._pre_cdr3_length = len(pre_cdr3_seq)
        self._pre_cdr3_match = self._pre_cdr3_length - distance.hamming(
            str(pre_cdr3_seq), str(pre_cdr3_germ))

        # Get the length of J after the CDR3
        self._post_cdr3_length = germlines.j_offset
        # Get the sequence and germline sequences after CDR3
        post_j = j_germ[-self.post_cdr3_length:]
        post_s = self.sequence[VGene.CDR3_OFFSET+len(self.cdr3):]

        # Calculate their match count
        self._post_cdr3_match = self.post_cdr3_length - distance.hamming(
            post_j, post_s)

    @property
    def has_possible_indel(self):
        # Start comparison on first full AA to the INDEL_WINDOW or CDR3,
        # whichever comes first
        if self._possible_indel:
            return True

        start = re.search('[ATCG]', self.sequence).start()
        end = VGene.CDR3_OFFSET
        germ = self.germline[start:end]
        seq = self.sequence[start:end]

        for i in range(0, len(germ) - self.INDEL_WINDOW + 1):
            g = germ[i:i+self.INDEL_WINDOW]
            s = seq[i:i+self.INDEL_WINDOW]
            if 'N' in g:
                dist = np.sum([
                    0 if gs == 'N' or gs == ss else 1 for gs, ss in zip(g, s)])
            else:
                dist = distance.hamming(g, s)
            if dist >= self.INDEL_MISMATCH_THRESHOLD * self.INDEL_WINDOW:
                return True

        return False
