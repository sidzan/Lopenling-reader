from collections import defaultdict
from typing import List, Optional, Iterable
from functools import reduce
from sefaria.model import abstract as abst
from sefaria.model import schema
from .ref_part import TermContext, LEAF_TRIE_ENTRY
from .referenceable_book_node import NamedReferenceableBookNode


class MatchTemplate(abst.Cloneable):
    """
    Template for matching a SchemaNode to a RawRef
    """
    def __init__(self, term_slugs, scope='combined'):
        self.term_slugs = term_slugs
        self.scope = scope

    def get_terms(self) -> Iterable[schema.NonUniqueTerm]:
        for slug in self.term_slugs:
            yield schema.NonUniqueTerm.init(slug)

    def serialize(self) -> dict:
        serial = {
            "term_slugs": [t.slug for t in self.get_terms()],
        }
        if self.scope != 'combined':
            serial['scope'] = self.scope
        return serial

    terms = property(get_terms)


class MatchTemplateTrie:
    """
    Trie for titles. Keys are titles from match_templates on nodes.
    E.g. if there is match template with term slugs ["term1", "term2"], term1 has title "Term 1", term2 has title "Term 2"
    then an entry in the trie would be {"Term 1": {"Term 2": ...}}
    """
    def __init__(self, lang, nodes=None, sub_trie=None, scope=None) -> None:
        """
        :param lang:
        :param nodes:
        :param sub_trie:
        :param scope: str. scope of the trie. if 'alone', take into account `match_templates` marked with scope "alone" or "any".
        """
        self.lang = lang
        self.scope = scope
        if nodes is not None:
            self.__init_with_nodes(nodes)
        else:
            self._trie = sub_trie

    def __init_with_nodes(self, nodes):
        self._trie = {}
        for node in nodes:
            is_index_level = getattr(node, 'index', False) and node == node.index.nodes
            for match_template in node.get_match_templates():
                if not is_index_level and self.scope != 'any' and match_template.scope != 'any' and self.scope != match_template.scope: continue
                curr_dict_queue = [self._trie]
                for term in match_template.terms:
                    if term is None:
                        try:
                            node_ref = node.ref()
                        except:
                            node_ref = node.get_primary_title('en')
                        print(f"{node_ref} has match_templates that reference slugs that don't exist. Check match_templates and fix.")
                        continue
                    len_curr_dict_queue = len(curr_dict_queue)
                    for _ in range(len_curr_dict_queue):
                        curr_dict = curr_dict_queue.pop(0)
                        curr_dict_queue += self.__get_sub_tries_for_term(term, curr_dict)
                # add nodes to leaves
                for curr_dict in curr_dict_queue:
                    leaf_node = NamedReferenceableBookNode(node.index if is_index_level else node)
                    if LEAF_TRIE_ENTRY in curr_dict:
                        curr_dict[LEAF_TRIE_ENTRY] += [leaf_node]
                    else:
                        curr_dict[LEAF_TRIE_ENTRY] = [leaf_node]

    @staticmethod
    def __get_sub_trie_for_new_key(key: str, curr_trie: dict) -> dict:
        if key in curr_trie:
            sub_trie = curr_trie[key]
        else:
            sub_trie = {}
            curr_trie[key] = sub_trie
        return sub_trie

    def __get_sub_tries_for_term(self, term: schema.NonUniqueTerm, curr_trie: dict) -> List[dict]:
        sub_tries = []
        for title in term.get_titles(self.lang):
            sub_tries += [self.__get_sub_trie_for_new_key(title, curr_trie)]
        # also add term's key to trie for lookups from context ref parts
        sub_tries += [self.__get_sub_trie_for_new_key(TermContext(term).key(), curr_trie)]
        return sub_tries

    def __getitem__(self, key):
        return self.get(key)        

    def get(self, key, default=None):
        sub_trie = self._trie.get(key, default)
        if sub_trie is None: return
        return MatchTemplateTrie(self.lang, sub_trie=sub_trie, scope=self.scope)

    def has_continuations(self, key: str, key_is_id=False) -> bool:
        """
        Does trie have continuations for `key`?
        :param key: key to look up in trie. may need to be split into multiple keys to find a continuation.
        :param key_is_id: True if key is ID that cannot be split into smaller keys (e.g. slug).
        TODO currently not allowing partial matches here but theoretically possible
        """
        conts, _ = self.get_continuations(key, default=None, key_is_id=key_is_id, allow_partial=False)
        return conts is not None

    @staticmethod
    def _merge_two_tries(a, b):
        "merges b into a"
        for key in b:
            if key in a:
                if isinstance(a[key], dict) and isinstance(b[key], dict):
                    MatchTemplateTrie._merge_two_tries(a[key], b[key])
                elif a[key] == b[key]:
                    pass  # same leaf value
                elif isinstance(a[key], list) and isinstance(b[key], list):
                    a[key] += b[key]
                else:
                    raise Exception('Conflict in _merge_two_tries')
            else:
                a[key] = b[key]
        return a

    @staticmethod
    def _merge_n_tries(*tries):
        if len(tries) == 1:
            return tries[0]
        return reduce(MatchTemplateTrie._merge_two_tries, tries)

    def get_continuations(self, key: str, default=None, key_is_id=False, allow_partial=False):
        continuations, partial_key_end_list = self._get_continuations_recursive(key, key_is_id=key_is_id, allow_partial=allow_partial)
        if len(continuations) == 0:
            return default, None
        merged = self._merge_n_tries(*continuations)
        # TODO unclear how to 'merge' partial_key_end_list. Currently will only work if there's one continuation
        partial_key_end = partial_key_end_list[0] if len(partial_key_end_list) == 1 else None
        return MatchTemplateTrie(self.lang, sub_trie=merged, scope=self.scope), partial_key_end

    def _get_continuations_recursive(self, key: str, prev_sub_tries=None, key_is_id=False, has_partial_matches=False, allow_partial=False):
        from sefaria.utils.hebrew import get_prefixless_inds
        import re

        prev_sub_tries = prev_sub_tries or self._trie
        if key_is_id:
            # dont attempt to split key
            next_sub_tries = [prev_sub_tries[key]] if key in prev_sub_tries else []
            return next_sub_tries, []
        next_sub_tries = []
        partial_key_end_list = []
        key = key.strip()
        starti_list = [0]
        if self.lang == 'he' and len(key) >= 4:
            # In AddressType.get_all_possible_sections_from_string(), we prevent stripping of prefixes from AddressInteger. No simple way to do that with terms that take the place of AddressInteger (e.g. Bavli Perek). len() check is a heuristic.
            starti_list += get_prefixless_inds(key)
        for starti in starti_list:
            for match in reversed(list(re.finditer(r'(\s+|$)', key[starti:]))):
                endi = match.start() + starti
                sub_key = key[starti:endi]
                if sub_key not in prev_sub_tries: continue
                if endi == len(key):
                    next_sub_tries += [prev_sub_tries[sub_key]]
                    partial_key_end_list += [None]
                    continue
                temp_sub_tries, temp_partial_key_end_list = self._get_continuations_recursive(key[endi:], prev_sub_tries[sub_key], has_partial_matches=True, allow_partial=allow_partial)
                next_sub_tries += temp_sub_tries
                partial_key_end_list += temp_partial_key_end_list

        if has_partial_matches and len(next_sub_tries) == 0 and allow_partial and isinstance(prev_sub_tries, dict):
            # partial match without any complete matches
            return [prev_sub_tries], [key]
        if len(partial_key_end_list) > 1:
            # currently we don't consider partial keys if there's more than one match
            full_key_matches = list(filter(lambda x: x[1] is None, zip(next_sub_tries, partial_key_end_list)))
            if len(full_key_matches) == 0:
                return [], []
            next_sub_tries, partial_key_end_list = zip(*full_key_matches)
        return next_sub_tries, partial_key_end_list

    def __contains__(self, key):
        return key in self._trie

    def __iter__(self):
        for item in self._trie:
            yield item


class MatchTemplateGraph:
    """
    DAG which represents connections between terms in index titles
    where each connection is a pair of consecutive terms
    """
    def __init__(self, nodes: List[schema.TitledTreeNode]):
        self._graph = defaultdict(set)
        for node in nodes:
            for match_template in node.get_match_templates():
                if len(match_template.term_slugs) < 2: continue
                terms = list(match_template.terms)
                for iterm, term in enumerate(terms[:-1]):
                    next_term = terms[iterm+1]
                    if term.ref_part_role == 'structural' and next_term.ref_part_role == 'structural':
                        self._graph[term.slug].add(next_term.slug)

    def parent_has_child(self, parent: str, child: str) -> bool:
        """
        For case where context is Yerushalmi Berakhot 1:1 and ref is Shabbat 1:1. Want to infer that we're referring to
        Yerushalmi Shabbat
        """
        return child in self._graph[parent]

    def do_parents_share_child(self, parent1: str, parent2: str, child: str) -> bool:
        """
        For case where context is Yerushalmi Berakhot 1:1 and ref is Bavli 2a. Want to infer that we're referring to
        Bavli Berakhot 2a b/c Yerushalmi and Bavli share child Berakhot
        """
        return self.parent_has_child(parent1, child) and self.parent_has_child(parent2, child)

    def get_parent_for_children(self, context_match_templates: List[MatchTemplate], input_slugs: list) -> Optional[str]:
        for template in context_match_templates:
            for context_slug in template.term_slugs:
                for input_slug in input_slugs:
                    if self.parent_has_child(context_slug, input_slug):
                        return context_slug

    def get_shared_child(self, context_match_templates: List[MatchTemplate], input_slugs: List[str]) -> Optional[str]:
        for template in context_match_templates:
            for i, context_slug in enumerate(template.term_slugs[:-1]):
                next_context_slug = template.term_slugs[i+1]
                for input_slug in input_slugs:
                    if self.do_parents_share_child(context_slug, input_slug, next_context_slug):
                        return next_context_slug


