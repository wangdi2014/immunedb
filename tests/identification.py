import sys
from Bio import SeqIO
from sldb.identification.vdj_sequence import VDJSequence
import sldb.identification.v_ties as v_ties
import sldb.util.lookups as lookups


if __name__ == '__main__':
    v_germlines = {}
    with open(sys.argv[1]) as fh:
        for vr in SeqIO.parse(fh, 'fasta'):
            v_germlines[vr.id] = str(vr.seq).upper()

    for record in SeqIO.parse(sys.argv[2], 'fasta'):
        print record.description
        vdj = VDJSequence(record.description, record.seq, 'presto' in
                          record.description, v_germlines)
        if vdj.j_gene is not None and vdj.v_gene is not None:
            print 'v_gene     :', vdj.v_gene
            print 'j_gene     :', vdj.j_gene
            print 'cdr3 len   :', len(vdj.cdr3)
            print 'cdr3       :', vdj.cdr3
            print 'cdr3_aa    :', lookups.aas_from_nts(vdj.cdr3, '')
            print 'germ       :', vdj.germline
            print 'seq        :', vdj.sequence
            print 'v_len      :', vdj.v_length
            print 'v_match    :', vdj.v_match
            print 'v_perc     :', vdj.v_match / float(vdj.v_length)
            print 'gaps       :', vdj.num_gaps
            print 'pads       :', vdj.pad_length
            print 'pre_cdr3_len:', vdj.pre_cdr3_length
            print 'pre_cdr3_mth:', vdj.pre_cdr3_match
            print 'j_len      :', vdj.j_length
            print 'j_match    :', vdj.j_match
            print 'post_cdr3_len:', vdj.post_cdr3_length
            print 'post_cdr3_mth:', vdj.post_cdr3_match
            print ''
        else:
            print 'No result'
