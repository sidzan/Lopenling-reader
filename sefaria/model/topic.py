from typing import Union
from . import abstract as abst
from .schema import AbstractTitledObject, TitleGroup
from .text import Ref
from sefaria.system.exceptions import DuplicateRecordError
import logging
import regex as re
logger = logging.getLogger(__name__)


class Topic(abst.AbstractMongoRecord, AbstractTitledObject):
    collection = 'topics'
    history_noun = 'topic'
    slug_fields = ['slug']
    title_group = None
    required_attrs = [
        'slug',
        'titles',
    ]
    optional_attrs = [
        'alt_ids',
        'properties',
        'description',
        'isTopLevelDisplay',
        'displayOrder',
        'numSources',
        'shouldDisplay',
        'parasha',  # name of parsha as it appears in `parshiot` collection
        'ref',  # for topics with refs associated with them, this stores the tref (e.g. for a parashah)
        'good_to_promote',
        'disambiguation',
        'description_published',  # bool to keep track of which descriptions we've vetted
    ]
    uncategorized_topic = 'uncategorized0000'

    @staticmethod
    def init(slug:str) -> 'Topic':
        """
        Convenience func to avoid using .load() when you're only passing a slug
        :param slug:
        :return:
        """
        return Topic().load({'slug': slug})

    def _set_derived_attributes(self):
        self.set_titles(getattr(self, "titles", None))

    def set_titles(self, titles):
        self.title_group = TitleGroup(titles)

    def title_is_transliteration(self, title, lang):
        return self.title_group.get_title_attr(title, lang, 'transliteration') is not None

    def get_types(self, types=None, curr_path=None, search_slug_set=None):
        """
        WARNING: Expensive, lots of database calls
        Checks if `self` has `topic_slug` as an ancestor when traversing `is-a` links
        :param types: set(str), current known types, for recursive calls
        :param curr_path: current path of this recursive call
        :param search_slug_set: if passed, will return early once/if any element of `search_slug_set` is found
        :return: set(str)
        """
        types = types or {self.slug}
        curr_path = curr_path or [self.slug]
        isa_set = {l.toTopic for l in IntraTopicLinkSet({"fromTopic": self.slug, "linkType": TopicLinkType.isa_type})}
        types |= isa_set
        if search_slug_set is not None and len(search_slug_set.intersection(types)) > 0:
            return types
        for isa_slug in isa_set:
            new_path = [p for p in curr_path]
            if isa_slug in new_path:
                logger.warning("Circular path starting from {} and ending at {} detected".format(new_path[0], isa_slug))
                continue
            new_path += [isa_slug]
            new_topic = Topic.init(isa_slug)
            if new_topic is None:
                logger.warning("{} is None. Current path is {}".format(isa_slug, ', '.join(new_path)))
                continue
            new_topic.get_types(types, new_path, search_slug_set)
        return types

    def get_leaf_nodes(self, linkType='is-a'):
        leaves = []
        children = [l.fromTopic for l in IntraTopicLinkSet({"toTopic": self.slug, "linkType": linkType})]
        if len(children) == 0:
            return [self]
        else:
            for slug in children:
                child_topic = Topic.init(slug)
                if child_topic is None:
                    logger.warning(f"{slug} is None")
                    continue
                leaves += child_topic.get_leaf_nodes(linkType)
        return leaves

    def has_types(self, search_slug_set):
        """
        WARNING: Expensive, lots of database calls
        Checks if `self` has any slug in `search_slug_set` as an ancestor when traversing `is-a` links
        :param search_slug_set: set(str), slugs to search for. returns True if any slug is found
        :return: bool
        """
        types = self.get_types(search_slug_set=search_slug_set)
        return len(search_slug_set.intersection(types)) > 0

    def should_display(self):
        return getattr(self, 'shouldDisplay', True) and getattr(self, 'numSources', 0) > 0

    def set_slug(self, new_slug):
        slug_field = self.slug_fields[0]
        old_slug = getattr(self, slug_field)
        setattr(self, slug_field, new_slug)
        setattr(self, slug_field, self.normalize_slug_field(slug_field))
        self.merge(old_slug)

    def merge(self, other: Union['Topic', str]) -> None:
        """
        :param other: Topic or old slug to migrate from
        :return: None
        """
        from sefaria.system.database import db
        if other is None:
            return
        other_slug = other if isinstance(other, str) else other.slug
        if other_slug == self.slug:
            logger.warning('Cant merge slug into itself')

        # links
        for link in TopicLinkSetHelper.find({"$or": [{"toTopic": other_slug}, {"fromTopic": other_slug}]}):
            if link.linkType == TopicLinkType.isa_type and link.toTopic == Topic.uncategorized_topic:
                # no need to merge uncategorized is-a links
                link.delete()
                continue
            attr = 'toTopic' if link.toTopic == other_slug else 'fromTopic'
            setattr(link, attr, self.slug)
            if getattr(link, 'fromTopic', None) == link.toTopic:
                # self-link
                link.delete()
                continue
            try:
                link.save()
            except DuplicateRecordError:
                link.delete()
            except AssertionError as e:
                link.delete()
                logger.warning('While merging {} into {}, link assertion failed with message "{}"'.format(other_slug, self.slug, str(e)))

        # source sheets
        db.sheets.update_many({'topics.slug': other_slug}, {"$set": {'topics.$[element].slug': self.slug}}, array_filters=[{"element.slug": other_slug}])

        if isinstance(other, Topic):
            # titles
            for title in other.titles:
                if title.get('primary', False):
                    del title['primary']
            self.titles += other.titles

            # dictionary attributes
            for dict_attr in ['alt_ids', 'properties']:
                temp_dict = getattr(self, dict_attr, {})
                for k, v in getattr(other, dict_attr, {}).items():
                    if k in temp_dict:
                        logger.warning('Key {} with value {} already exists in {} for topic {}. Current value is {}'.format(k, v, dict_attr, self.slug, temp_dict[k]))
                        continue
                    temp_dict[k] = v
                if len(temp_dict) > 0:
                    setattr(self, dict_attr, temp_dict)
            setattr(self, 'numSources', getattr(self, 'numSources', 0) + getattr(other, 'numSources', 0))

            # everything else
            already_merged = ['slug', 'titles', 'alt_ids', 'properties', 'numSources']
            for attr in filter(lambda x: x not in already_merged, self.required_attrs + self.optional_attrs):
                if not getattr(self, attr, False) and getattr(other, attr, False):
                    setattr(self, attr, getattr(other, attr))
            self.save()
            other.delete()

    def link_set(self, _class='intraTopic', query_kwargs: dict = None, **kwargs):
        """
        :param str _class: could be 'intraTopic' or 'refTopic' or `None` (see `TopicLinkHelper`)
        :param query_kwargs: dict of extra query keyword arguments
        :return: link set of topic links to `self`
        """
        intra_link_query = {"$or": [{"fromTopic": self.slug}, {"toTopic": self.slug}]}
        if query_kwargs is not None:
            intra_link_query.update(query_kwargs)
        if _class == 'intraTopic':
            kwargs['record_kwargs'] = {'context_slug': self.slug}
            return IntraTopicLinkSet(intra_link_query, **kwargs)
        elif _class == 'refTopic':
            ref_link_query = {'toTopic': self.slug}
            if query_kwargs is not None:
                ref_link_query.update(query_kwargs)
            return RefTopicLinkSet(ref_link_query, **kwargs)
        elif _class is None:
            kwargs['record_kwargs'] = {'context_slug': self.slug}
            return TopicLinkSetHelper.find(intra_link_query, **kwargs)

    def contents(self, **kwargs):
        mini = kwargs.get('minify', False)
        d = {'slug': self.slug} if mini else super(Topic, self).contents(**kwargs)
        d['primaryTitle'] = {}
        for lang in ('en', 'he'):
            d['primaryTitle'][lang] = self.get_primary_title(lang=lang, with_disambiguation=kwargs.get('with_disambiguation', True))
        return d

    def get_primary_title(self, lang='en', with_disambiguation=True):
        title = super(Topic, self).get_primary_title(lang=lang)
        if with_disambiguation:
            disambig_dict = getattr(self, 'disambiguation', {})
            if disambig_dict.get(lang, False):
                title += ' ({})'.format(disambig_dict[lang])
        return title

    def get_property(self, property):
        properties = getattr(self, 'properties', {})
        if property not in properties:
            return None, None
        return properties[property]['value'], properties[property]['dataSource']


    @staticmethod
    def get_uncategorized_slug_set():
        return {t.fromTopic for t in IntraTopicLinkSet({'toTopic': Topic.uncategorized_topic, 'linkType': 'is-a'})}

    def __str__(self):
        return self.get_primary_title("en")

    def __repr__(self):
        return "{}.init('{}')".format(self.__class__.__name__, self.slug)


class TopicSet(abst.AbstractMongoSet):
    recordClass = Topic


class TopicLinkHelper(object):
    """
    Used to collect attributes and functions that are useful for both IntraTopicLink and RefTopicLink
    Decided against superclass arch b/c instantiated objects will be of type super class.
    This is inconvenient when validating the attributes of object before saving (since subclasses have different required attributes)
    """
    collection = 'topic_links'
    required_attrs = [
        'toTopic',
        'linkType',
        'class',  # can be 'intraTopic' or 'refTopic'
        'dataSource',

    ]
    optional_attrs = [
        'generatedBy',
        'order'
    ]

    @staticmethod
    def init_by_class(topic_link, context_slug=None):
        """
        :param topic_link: dict from `topic_links` collection
        :return: either instance of IntraTopicLink or RefTopicLink based on 'class' field of `topic_link`
        """
        if topic_link['class'] == 'intraTopic':
            return IntraTopicLink(topic_link, context_slug=context_slug)
        if topic_link['class'] == 'refTopic':
            return RefTopicLink(topic_link)


class IntraTopicLink(abst.AbstractMongoRecord):
    collection = TopicLinkHelper.collection
    required_attrs = TopicLinkHelper.required_attrs + ['fromTopic']
    optional_attrs = TopicLinkHelper.optional_attrs
    valid_links = []

    def __init__(self, attrs=None, context_slug=None):
        """

        :param attrs:
        :param str context_slug: if this link is being used in a specific context, give the topic slug which represents the context. used to set if the link should be considered inverted
        """
        super(IntraTopicLink, self).__init__(attrs=attrs)
        self.context_slug = context_slug

    def _normalize(self):
        setattr(self, "class", "intraTopic")

    def _pre_save(self):
        pass

    def _validate(self):
        super(IntraTopicLink, self)._validate()

        # check everything exists
        link_type = TopicLinkType().load({"slug": self.linkType})
        assert link_type is not None, "Link type '{}' does not exist".format(self.linkType)
        from_topic = Topic.init(self.fromTopic)
        assert from_topic is not None, "fromTopic '{}' does not exist".format(self.fromTopic)
        to_topic = Topic.init(self.toTopic)
        assert to_topic is not None, "toTopic '{}' does not exist".format(self.toTopic)
        data_source = TopicDataSource().load({"slug": self.dataSource})
        assert data_source is not None, "dataSource '{}' does not exist".format(self.dataSource)

        # check for duplicates
        duplicate = IntraTopicLink().load({"linkType": self.linkType, "fromTopic": self.fromTopic, "toTopic": self.toTopic,
                 "class": getattr(self, 'class'), "_id": {"$ne": getattr(self, "_id", None)}})
        if duplicate is not None:
            raise DuplicateRecordError(
                "Duplicate intra topic link for linkType '{}', fromTopic '{}', toTopic '{}'".format(
                    self.linkType, self.fromTopic, self.toTopic))

        if link_type.slug == link_type.inverseSlug:
            duplicate_inverse = IntraTopicLink().load({"linkType": self.linkType, "toTopic": self.fromTopic, "fromTopic": self.toTopic,
             "class": getattr(self, 'class'), "_id": {"$ne": getattr(self, "_id", None)}})
            if duplicate_inverse is not None:
                raise DuplicateRecordError(
                    "Duplicate intra topic link in the inverse direction of the symmetric linkType '{}', fromTopic '{}', toTopic '{}' exists".format(
                        duplicate_inverse.linkType, duplicate_inverse.fromTopic, duplicate_inverse.toTopic))

        # check types of topics are valid according to validFrom/To
        if getattr(link_type, 'validFrom', False):
            assert from_topic.has_types(set(link_type.validFrom)), "from topic '{}' does not have valid types '{}' for link type '{}'. Instead, types are '{}'".format(self.fromTopic, ', '.join(link_type.validFrom), self.linkType, ', '.join(from_topic.get_types()))
        if getattr(link_type, 'validTo', False):
            assert to_topic.has_types(set(link_type.validTo)), "to topic '{}' does not have valid types '{}' for link type '{}'. Instead, types are '{}'".format(self.toTopic, ', '.join(link_type.validTo), self.linkType, ', '.join(to_topic.get_types()))

        # assert this link doesn't create circular paths (in is_a link type)
        # should consider this test also for other non-symmetric link types such as child-of
        if self.linkType == TopicLinkType.isa_type:
            to_topic = Topic.init(self.toTopic)
            ancestors = to_topic.get_types()
            assert self.fromTopic not in ancestors, "{} is an is-a ancestor of {} creating an illogical circle in the topics graph, here are {} ancestors: {}".format(self.fromTopic, self.toTopic, self.toTopic, ancestors)

    def contents(self, **kwargs):
        d = super(IntraTopicLink, self).contents(**kwargs)
        if self.context_slug is not None:
            d['isInverse'] = self.is_inverse
            d['topic'] = self.topic
            del d['toTopic']
            del d['fromTopic']
            if d.get('order', None) is not None:
                d['order']['tfidf'] = self.tfidf
                d['order'].pop('toTfidf', None)
                d['order'].pop('fromTfidf', None)
        return d

    # PROPERTIES

    def get_is_inverse(self):
        return self.context_slug == self.toTopic

    def get_topic(self):
        return self.fromTopic if self.is_inverse else self.toTopic

    def get_tfidf(self):
        order = getattr(self, 'order', {})
        return order.get('fromTfidf' if self.is_inverse else 'toTfidf', 0)

    topic = property(get_topic)
    tfidf = property(get_tfidf)
    is_inverse = property(get_is_inverse)


class RefTopicLink(abst.AbstractMongoRecord):
    collection = TopicLinkHelper.collection
    required_attrs = TopicLinkHelper.required_attrs + ['ref', 'expandedRefs', 'is_sheet']  # is_sheet  and expandedRef attrs are defaulted automatically in normalize
    optional_attrs = TopicLinkHelper.optional_attrs + ['text']

    def _normalize(self):
        super(RefTopicLink, self)._normalize()
        self.is_sheet = bool(re.search("Sheet \d+$", self.ref))
        setattr(self, "class", "refTopic")
        if self.is_sheet:
            self.expandedRefs = [self.ref]
        else:  # Ref is a regular Sefaria Ref
            self.expandedRefs = [r.normal() for r in Ref(self.ref).all_segment_refs()]

    def _pre_save(self):
        if getattr(self, "_id", None) is None:
            # check for duplicates
            duplicate = RefTopicLink().load(
                {"linkType": self.linkType, "ref": self.ref, "toTopic": self.toTopic, "dataSource": getattr(self, 'dataSource', {"$exists": False}),
                 "class": getattr(self, 'class')})
            if duplicate is not None:
                raise DuplicateRecordError("Duplicate ref topic link for linkType '{}', ref '{}', toTopic '{}', dataSource '{}'".format(
                self.linkType, self.ref, self.toTopic, getattr(self, 'dataSource', 'N/A')))


class TopicLinkSetHelper(object):

    @staticmethod
    def init_query(query, link_class):
        query = query or {}
        query['class'] = link_class
        return query

    @staticmethod
    def find(query=None, page=0, limit=0, sort=[("_id", 1)], proj=None, record_kwargs=None):
        from sefaria.system.database import db
        record_kwargs = record_kwargs or {}
        raw_records = getattr(db, TopicLinkHelper.collection).find(query, proj).sort(sort).skip(page * limit).limit(limit)
        return [TopicLinkHelper.init_by_class(r, **record_kwargs) for r in raw_records]


class IntraTopicLinkSet(abst.AbstractMongoSet):
    recordClass = IntraTopicLink

    def __init__(self, query=None, *args, **kwargs):
        query = TopicLinkSetHelper.init_query(query, 'intraTopic')
        super().__init__(query=query, *args, **kwargs)


class RefTopicLinkSet(abst.AbstractMongoSet):
    recordClass = RefTopicLink

    def __init__(self, query=None, *args, **kwargs):
        query = TopicLinkSetHelper.init_query(query, 'refTopic')
        super().__init__(query=query, *args, **kwargs)


class TopicLinkType(abst.AbstractMongoRecord):
    collection = 'topic_link_types'
    slug_fields = ['slug', 'inverseSlug']
    required_attrs = [
        'slug',
        'inverseSlug',
        'displayName',
        'inverseDisplayName'
    ]
    optional_attrs = [
        'pluralDisplayName',
        'inversePluralDisplayName',
        'alt_ids',
        'inverse_alt_ids',
        'shouldDisplay',
        'inverseShouldDisplay',
        'groupRelated',
        'inverseGroupRelated',
        'devDescription',
        'validFrom',
        'validTo'
    ]
    related_type = 'related-to'
    isa_type = 'is-a'

    def _validate(self):
        super(TopicLinkType, self)._validate()
        # Check that validFrom and validTo contain valid topic slugs if exist

        for validToTopic in getattr(self, 'validTo', []):
            assert Topic.init(validToTopic) is not None, "ValidTo topic '{}' does not exist".format(self.validToTopic)

        for validFromTopic in getattr(self, 'validFrom', []):
            assert Topic.init(validFromTopic) is not None, "ValidTo topic '{}' does not exist".format(
                self.validFrom)

    def get(self, attr, is_inverse, default=None):
        attr = 'inverse{}{}'.format(attr[0].upper(), attr[1:]) if is_inverse else attr
        return getattr(self, attr, default)


class TopicLinkTypeSet(abst.AbstractMongoSet):
    recordClass = TopicLinkType


class TopicDataSource(abst.AbstractMongoRecord):
    collection = 'topic_data_sources'
    slug_fields = ['slug']
    required_attrs = [
        'slug',
        'displayName',
    ]
    optional_attrs = [
        'url',
        'description',
    ]


class TopicDataSourceSet(abst.AbstractMongoSet):
    recordClass = TopicDataSource
