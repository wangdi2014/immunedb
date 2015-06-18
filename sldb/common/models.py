import datetime
import hashlib

from sqlalchemy import (Column, Boolean, Integer, String, Text, Date, DateTime,
                        ForeignKey, UniqueConstraint, Index, event, func)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import ColumnProperty, relationship, backref
from sqlalchemy.orm.interfaces import MapperExtension
from sqlalchemy.dialects.mysql import TEXT, MEDIUMTEXT, BINARY

from sldb.common.settings import DATABASE_SETTINGS

BaseMaster = declarative_base(
    metadata=DATABASE_SETTINGS['master_metadata'])
BaseData = declarative_base(
    metadata=DATABASE_SETTINGS['data_metadata'])
MAX_CDR3_NTS = 96
MAX_CDR3_AAS = int(MAX_CDR3_NTS / 3)
CDR3_OFFSET = 309


class Study(BaseMaster):
    """A high-level study such as one studying Lupus.

    :param int id: An auto-assigned unique identifier for the study
    :param str name: A unique name for the study
    :param str info: Optional information about the study

    """
    __tablename__ = 'studies'
    __table_args__ = {'mysql_engine': 'TokuDB'}

    id = Column(Integer, primary_key=True)
    # The name of the study
    name = Column(String(length=128), unique=True)
    # Some arbitrary information if necessary
    info = Column(String(length=1024))


class Subject(BaseMaster):
    """A subject which was sampled for a study.

    :param int id: An auto-assigned unique identifier for the subject
    :param str identifier: An identifier for the subject as defined by \
        the experimenter
    :param int study_id: The ID of the study under which the subject was \
        sampled
    :param Relationship study: Reference to the associated :py:class:`Study` \
        instance

    """
    __tablename__ = 'subjects'
    __table_args__ = (UniqueConstraint('study_id', 'identifier'),
                      {'mysql_engine': 'TokuDB'})

    id = Column(Integer, primary_key=True)

    identifier = Column(String(64))
    study_id = Column(Integer, ForeignKey(Study.id))
    study = relationship(Study, backref=backref('subjects',
                         order_by=identifier))


class Sample(BaseMaster):
    """A sample taken from a single subject, tissue, and subset.

    :param int id: An auto-assigned unique identifier for the sample
    :param str name: A unique name for the sample as defined by the \
        experimenter
    :param str info: Optional information about the sample
    :param date date: The date the sample was taken

    :param int study_id: The ID of the study under which the subject was \
        sampled
    :param Relationship study: Reference to the associated :py:class:`Study` \
        instance

    :param int subject_id: The ID of the subject from which the sample was \
        taken
    :param Relationship subject: Reference to the associated \
        :py:class:`Subject` instance


    :param str tissue: The tissue of the sample
    :param str subset: The tissue subset of the sample
    :param str disease: The known disease(s) present in the sample
    :param str lab: The lab which acquired the sample
    :param str experimenter: The experimenters name who took the sample

    """
    __tablename__ = 'samples'
    __table_args__ = {'mysql_engine': 'TokuDB'}

    id = Column(Integer, primary_key=True)
    name = Column(String(128), unique=True)
    info = Column(String(1024))

    date = Column(Date, nullable=False)

    study_id = Column(Integer, ForeignKey(Study.id))
    study = relationship(Study, backref=backref('samples', order_by=(date,
                                                name)))

    subject_id = Column(Integer, ForeignKey(Subject.id), index=True)
    subject = relationship(Subject, backref=backref('samples',
                           order_by=(id)))
    subset = Column(String(128))
    tissue = Column(String(16))
    disease = Column(String(32))
    lab = Column(String(128))
    experimenter = Column(String(128))


class SampleStats(BaseData):
    """Aggregate statistics for a sample.  This exists to reduce the time
    queries take for a sample.

    :param int sample_id: The ID of the sample for which the statistics were \
        generated
    :param Relationship sample: Reference to the associated \
        :py:class:`Sample` instance

    :param str filter_type: The type of filter for the statistics
        (e.g. functional)
    :param bool outliers: If outliers were included in the statistics
    :param bool full_reads: If only full reads were included in the statistics

    :param str v_identity_dist: Distribution of V gene identity
    :param str v_match_dist: Distribution of V gene match count
    :param str v_length_dist: Distribution of V gene total length
    :param str j_match_dist: Distribution of J gene match count
    :param str j_length_dist: Distribution of J gene total length
    :param str v_gene_dist: Distribution of V-gene assignments
    :param str j_gene_dist: Distribution of J-gene assignments
    :param str copy_number_dist: Distribution of copy number
    :param str cdr3_length_dist: Distribution of CDR3 lengths

    :param int sequence_cnt: The total number of sequences
    :param int in_frame_cnt: The number of in-frame sequences
    :param int stop_cnt: The number of sequences containing a stop codon
    :param int functional_cnt: The number of functional sequences
    :param int no_result_cnt: The number of invalid sequences

    """
    __tablename__ = 'sample_stats'
    __table_args__ = {'mysql_engine': 'TokuDB'}

    sample_id = Column(Integer, ForeignKey(Sample.id),
                       primary_key=True)
    sample = relationship(Sample, backref=backref('sample_stats',
                          order_by=sample_id))

    filter_type = Column(String(length=255), primary_key=True)
    outliers = Column(Boolean, primary_key=True)
    full_reads = Column(Boolean, primary_key=True)

    v_identity_dist = Column(MEDIUMTEXT)

    v_match_dist = Column(MEDIUMTEXT)
    v_length_dist = Column(MEDIUMTEXT)

    j_match_dist = Column(MEDIUMTEXT)
    j_length_dist = Column(MEDIUMTEXT)

    v_gene_dist = Column(MEDIUMTEXT)
    j_gene_dist = Column(MEDIUMTEXT)

    copy_number_dist = Column(MEDIUMTEXT)
    cdr3_length_dist = Column(MEDIUMTEXT)

    quality_dist = Column(MEDIUMTEXT)

    sequence_cnt = Column(Integer)
    in_frame_cnt = Column(Integer)
    stop_cnt = Column(Integer)
    functional_cnt = Column(Integer)
    no_result_cnt = Column(Integer)


class Clone(BaseData):
    """A group of sequences likely originating from the same germline

    :param int id: An auto-assigned unique identifier for the clone
    :param str v_gene: The V-gene assigned to the sequence
    :param str j_gene: The J-gene assigned to the sequence
    :param str cdr3_nt: The consensus nucleotides for the clone
    :param int cdr3_num_nts: The number of nucleotides in the group's CDR3
    :param str cdr3_aa: The amino-acid sequence of the group's CDR3
    :param int subject_id: The ID of the subject from which the sample was \
        taken
    :param Relationship subject: Reference to the associated \
        :py:class:`Subject` instance
    :param str germline: The germline sequence for this sequence
    :param str tree: The textual representation of the clone's lineage tree

    """
    __tablename__ = 'clones'
    __table_args__ = (Index('size_bucket', 'v_gene', 'j_gene',
                            'subject_id', 'cdr3_num_nts'),
                      Index('aa_bucket', 'v_gene', 'j_gene',
                            'subject_id', 'cdr3_aa'),
                      {'mysql_engine': 'TokuDB'})
    id = Column(Integer, primary_key=True)

    v_gene = Column(String(length=512), index=True)
    j_gene = Column(String(length=128), index=True)

    cdr3_nt = Column(String(length=MAX_CDR3_NTS))
    cdr3_num_nts = Column(Integer, index=True)
    cdr3_aa = Column(String(length=MAX_CDR3_AAS))

    subject_id = Column(Integer, ForeignKey(Subject.id), index=True)
    subject = relationship(Subject, backref=backref('clones',
                           order_by=(v_gene, j_gene, cdr3_num_nts, cdr3_aa)))

    germline = Column(String(length=1024))
    tree = Column(MEDIUMTEXT)

    @property
    def consensus_germline(self):
        return ''.join([
            self.germline[0:CDR3_OFFSET],
            self.cdr3_nt,
            self.germline[CDR3_OFFSET + self.cdr3_num_nts:]
        ])


class CloneStats(BaseData):
    """Stores statistics for a given clone and sample.  If sample is zero (0)
    the statistics are for the specified clone in all samples.

    :param int clone_id: The clone ID
    :param Relationship clone: Reference to the associated \
        :py:class:`Clone` instance

    :param int sample_id: The sample ID
    :param Relationship sample: Reference to the associated \
        :py:class:`Sample` instance

    :param int unique_cnt: The number of unique sequences in the clone in the \
        sample
    :param int total_cnt: The number of total sequences in the clone in the \
        sample

    :param str mutations: A JSON stanza of mutation count information
    :param str selection_pressure: A JSON stanza of selection pressure \
        information

    """
    __tablename__ = 'clone_stats'
    __table_args__ = {'mysql_engine': 'TokuDB'}

    clone_id = Column(Integer, ForeignKey(Clone.id), primary_key=True)
    clone = relationship(Clone)

    sample_id = Column(Integer, ForeignKey(Sample.id), primary_key=True)
    sample = relationship(Sample, backref=backref('clone_stats'))

    unique_cnt = Column(Integer)
    total_cnt = Column(Integer)

    mutations = Column(MEDIUMTEXT)
    selection_pressure = Column(MEDIUMTEXT)


class SequenceExtension(MapperExtension):
    """An extension to force sequences to be unique within a sample.  This
    cannot be achieved with a traditional UNIQUE constraint since the key would
    be too long.

    Also sets the ``cdr3_num_nts`` to the length of the `cdr3_nt`
    string

    """
    def before_insert(self, mapper, connection, instance):
        instance.sample_seq_hash = hashlib.sha1('{}{}'.format(
            instance.sample_id, instance.sequence)
        ).hexdigest()


class Sequence(BaseData):
    """Represents a single unique sequence.

    :param str sample_seq_hash: A key over ``sample_id`` and ``sequence`` so \
        the tuple can be maintained unique
    :param str seq_id: A unique identifier for the sequence as output by the \
        sequencer
    :param int sample_id: The ID of the sample from which this sequence came
    :param Relationship sample: Reference to the associated \
        :py:class:`Sample` instance
    :param str alignment: Alignment type (e.g. R1, R2, or R1+R2)
    :param bool probable_indel_or_misalign: If the sequence likely has an \
        indel or is a bad alignment

    :param str v_gene: The V-gene assigned to the sequence
    :param str j_gene: The J-gene assigned to the sequence

    :param int num_gaps: Number of inserted gaps
    :param int pad_length: The number of pad nucleotides added to the V end \
        of the sequence

    :param int v_match: The number of V-gene nucleotides matching the germline
    :param int v_length: The length of the V-gene segment prior to a streak \
        of mismatches in the CDR3
    :param int j_match: The number of J-gene nucleotides matching the germline
    :param int j_length: The length of the J-gene segment after a streak of \
        mismatches in the CDR3

    :param int pre_cdr3_length: The length of the V-gene prior to the CDR3
    :param int pre_cdr3_match: The number of V-gene nucleotides matching the \
        germline prior to the CDR3

    :param int post_cdr3_length: The length of the J-gene after to the CDR3
    :param int post_cdr3_match: The number of J-gene nucleotides matching the \
        germline after to the CDR3

    :param bool in_frame: If the sequence's CDR3 has a length divisible by 3
    :param bool functional: If the sequence is in-frame and contains no stop \
        codons
    :param bool stop: If the sequence contains a stop codon
    :param int copy_number: Number of reads identical to the sequence in the \
        same sample

    :param int cdr3_num_nts: The number of nucleotides in the CDR3
    :param str cdr3_nt: The nucleotides comprising the CDR3
    :param str cdr3_aa: The amino-acids comprising the CDR3
    :param str gap_method: The method used to gap the sequence (e.g. IGMT)

    :param str sequence: The (possibly-padded) sequence
    :param str quality: Optional Phred quality score (in Sanger format) for \
        each base in ``sequence``

    :param str germline: The germline sequence for this sequence

    :param int clone_id: The clone ID to which this sequence belongs
    :param Relationship clone: Reference to the associated :py:class:`Clone` \
        instance
    :param str mutations_from_clone: A JSON stanza with mutation information

    :param int copy_number_in_sample: The copy number of the sequence after \
        collapsing at the sample level.  Will be 0 if the sequence is \
        collapsed to another.
    :param str collapse_to_sample_seq_id: The sequence ID of the sequence \
        to which this sequence is collapsed at the sample level

    :param int copy_number_in_subject: The copy number of the sequence after \
        collapsing at the subject level.  Will be 0 if the sequence is \
        collapsed to another.
    :param int collapse_to_subject_sample_id: The sample ID of the sequence \
        to which this sequence is collapsed at the subject level
    :param str collapse_to_subject_seq_id: The sequence ID of the sequence \
        to which this sequence is collapsed at the subject level

    """
    __tablename__ = 'sequences'
    __table_args__ = (
        Index('genes', 'v_gene', 'j_gene'),
        Index('sample_collapse', 'collapse_to_sample_seq_id',
              'sample_id'),
        Index('subject_collapse',
              'collapse_to_subject_sample_id',
              'collapse_to_subject_seq_id'),
        Index('clone_by_subject', 'clone_id',
              'copy_number_in_subject'),
        {'mysql_engine': 'TokuDB'}
    )
    __mapper_args__ = {'extension': SequenceExtension()}

    sample_seq_hash = Column(String(40), unique=True, index=True)

    seq_id = Column(String(128), primary_key=True, index=True)
    sample_id = Column(Integer, ForeignKey(Sample.id), primary_key=True,
                       index=True)
    sample = relationship(Sample, backref=backref('sequences'))

    alignment = Column(String(length=6), index=True)
    partial_read = Column(Boolean, index=True)
    probable_indel_or_misalign = Column(Boolean, index=True)

    v_gene = Column(String(512), index=True)
    j_gene = Column(String(512), index=True)

    num_gaps = Column(Integer)
    pad_length = Column(Integer)

    v_match = Column(Integer)
    v_length = Column(Integer)
    j_match = Column(Integer)
    j_length = Column(Integer)

    pre_cdr3_length = Column(Integer)
    pre_cdr3_match = Column(Integer)
    post_cdr3_length = Column(Integer)
    post_cdr3_match = Column(Integer)

    in_frame = Column(Boolean)
    functional = Column(Boolean, index=True)
    stop = Column(Boolean)
    copy_number = Column(Integer, index=True, server_default='0',
                         nullable=False)

    # This is just length(cdr3_nt) but is included for fast statistics
    # generation over the index
    cdr3_num_nts = Column(Integer, index=True)

    cdr3_nt = Column(String(MAX_CDR3_NTS))
    cdr3_aa = Column(String(MAX_CDR3_AAS), index=True)
    gap_method = Column(String(16))

    sequence = Column(String(length=1024), index=True)
    quality = Column(String(length=1024))

    germline = Column(String(length=1024))

    clone_id = Column(Integer, ForeignKey(Clone.id), index=True)
    clone = relationship(Clone, backref=backref('sequences',
                         order_by=seq_id))
    mutations_from_clone = Column(MEDIUMTEXT)

    copy_number_in_sample = Column(Integer, index=True, server_default='0',
                                   nullable=False)
    collapse_to_sample_seq_id = Column(String(128), index=True)

    copy_number_in_subject = Column(Integer, index=True, server_default='0',
                                    nullable=False)
    collapse_to_subject_sample_id = Column(Integer)
    collapse_to_subject_seq_id = Column(String(128))


class DuplicateSequence(BaseData):
    """A sequence which is a duplicate of a :py:class:`Sequence`.  This is
    used to minimize the size of the sequences table.  The ``copy_number``
    attribute of :py:class:`Sequence` instances is equal to the number of
    its duplicate sequences plus one.

    :param str seq_id: A unique identifier for the sequence as output by the \
        sequencer

    :param str duplicate_seq_id: The identifier of the sequence in the same \
        sample with the same sequence
    :param Relationship duplicate_seq: Reference to the associated \
        :py:class:`Sequence` instance of which this is a duplicate

    :param int sample_id: The ID of the sample from which this sequence came
    :param Relationship sample: Reference to the associated \
        :py:class:`Sample` instance

    """
    __tablename__ = 'duplicate_sequences'
    __table_args__ = {'mysql_engine': 'TokuDB'}

    seq_id = Column(String(length=128), primary_key=True)

    duplicate_seq_id = Column(String(length=128),
                              ForeignKey('sequences.seq_id'),
                              primary_key=True,
                              index=True)
    duplicate_seq = relationship(Sequence,
                                 backref=backref('duplicate_sequences',
                                                 order_by=duplicate_seq_id))

    sample_id = Column(Integer, ForeignKey(Sample.id),
                       primary_key=True)
    sample = relationship(Sample, backref=backref('duplicate_sequences',
                          order_by=seq_id))


class NoResult(BaseData):
    """A sequence which could not be match with a V or J.

    :param str seq_id: A unique identifier for the sequence as output by the \
        sequencer
    :param int sample_id: The ID of the sample from which this sequence came
    :param Relationship sample: Reference to the associated \
        :py:class:`Sample` instance
    :param str sequence: The sequence of the non-identifiable input

    """
    __tablename__ = 'noresults'
    __table_args__ = {'mysql_engine': 'TokuDB'}

    seq_id = Column(String(length=128), primary_key=True)

    sample_id = Column(Integer, ForeignKey(Sample.id),
                       primary_key=True)
    sample = relationship(Sample, backref=backref('noresults',
                          order_by=seq_id))

    sequence = Column(String(length=1024))


class ModificationLog(BaseData):
    """A log message for a database modification

    :param int id: The ID of the log message
    :param datetime datetime: The date and time of the message
    :param str action_type: A short string representing the action
    :param str info: A JSON stanza with log message information

    """
    __tablename__ = 'modification_logs'
    __table_args__ = {'mysql_engine': 'TokuDB'}

    id = Column(Integer, primary_key=True)
    datetime = Column(DateTime, default=datetime.datetime.utcnow)

    action_type = Column(String(length=128))
    info = Column(String(length=1024))

def check_string_length(cls, key, inst):
    prop = inst.prop
    # Only interested in simple columns, not relations
    if isinstance(prop, ColumnProperty) and len(prop.columns) == 1:
        col = prop.columns[0]
        # if we have string column with a length, install a length validator
        if isinstance(col.type, String) and col.type.length:
            max_length = col.type.length
            def set_(instance, value, oldvalue, initiator):
                if value is not None and len(value) > max_length:
                    raise ValueError('Length {} exceeds allowed {}'.format(
                        len(value), max_length))
            event.listen(inst, 'set', set_)

event.listen(BaseMaster, 'attribute_instrument', check_string_length)
event.listen(BaseData, 'attribute_instrument', check_string_length)
