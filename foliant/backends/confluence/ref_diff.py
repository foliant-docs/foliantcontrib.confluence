import re

from collections import namedtuple
from copy import copy
from difflib import SequenceMatcher
from pprint import pformat

from bs4 import BeautifulSoup
from bs4 import NavigableString
from bs4 import Tag

logger = None


def restore_refs(old_content: str,
                 new_content: str,
                 resolved_ids: list,
                 logger_,
                 resolve_changed: bool = False):
    '''
    Restore inline-comments from the old_content in the new_content and return
    the resulting html string.
    If `resolve_changed` is False — only restore the comments in the text that
    wasn't changed.
    '''
    # setting up global logger
    global logger
    logger = logger_

    old_bs = BeautifulSoup(old_content, 'html.parser')
    new_bs = BeautifulSoup(new_content, 'html.parser')
    if is_empty(new_bs):
        logger.debug('New content is empty, all inline comments will be omitted.')
        return new_content
    remove_outline_resolved(old_bs)
    ref_dict = generate_ref_dict(old_bs)
    new_strings = [s for s in new_bs.strings if s.strip()]
    old_strings = [s for s in old_bs.strings if s.strip()]
    places = find_place2(old_strings, new_strings, ref_dict)
    correct_places(places, new_strings)
    equal, not_equal = divide_places(places)
    restore_equal_refs(equal, new_strings)
    if not resolve_changed:
        insert_unequal_refs(not_equal, new_strings, resolved_ids)
    return str(new_bs)


def is_empty(soup):
    '''Check whether `soup` is an empty page (whitespaces ignored)'''
    for s in soup.strings:
        if s.strip():
            return False
    return True


def remove_outline_resolved(bs: BeautifulSoup):
    """
    Remove from bs object all inline comments which have nested comments inside
    them. These may be only resolved comments, and they cause a lot of trouble.
    In place.
    """
    logger.debug('remove_outline_resolved START')
    while True:
        restart = False
        comments = bs.find_all(re.compile('ac:inline-comment-marker'))
        for comment in comments:
            for child in comment.children:
                if child.name == 'ac:inline-comment-marker':
                    logger.debug(f'Comment has nested comments, removing: \n{comment}')
                    basic_unwrap(comment)
                    restart = True
                    break
            if restart:
                break
        else:
            logger.debug('remove_outline_resolved END')
            return


def basic_unwrap(element):
    """
    Unwrap element from its tag in place. Concatenate adjacent NavigableStrings
    which may have appeared after anwrapping:

    <b>'One '<to_unwrap>' Two '</to_unwrap>' Three'</b>
    <b>'One '' Two '' Three'</b>
    <b>'One  Two  Three'</b>
    """
    parent = element.parent
    element.unwrap()
    groupped = []
    accumulate = False
    for el in parent.contents:
        if isinstance(el, NavigableString):
            if accumulate:
                groupped[-1].append(el)
            else:
                groupped.append([el])
                accumulate = True
        else:
            accumulate = False
    groupped = [g for g in groupped if len(g) > 1]
    for g in groupped:
        g[0].replace_with(''.join(g))
        g.pop(0)
        for i in g:
            i.extract()


def generate_ref_dict(bs: BeautifulSoup) -> dict:
    '''
    Receives a BeautifulSoup object and generates a dictionary with info about
    inline comments.

    Output dictionary structure:

    Key: python id of a string, which contains the inline comment. It's one of
         the strings that may be obtained by BeautifulSoup.strings method.
    Value: {info_dict}, dictionary with info on the inline comment.

    {info_dict} structure:

    {
    'full':    Full unwrapped NavigableString which contained inline comment. It
               is in fact right now a part of the bs tree.
    'before':  NavigableString that was before the inline comment until next tag
               or end of parent OR another {info_dict} if there were several
               comments in one paragraph.
    'comment': The inline comment tag which was unwrapped, with commented text
               included.
    'after':   NavigableString that was after the inline comment until next tag
               or end of parent.
    'ref_id':  For convenience, the id of a comment from the 'ac:ref' attribute.
    }
    '''
    logger.debug('generate_ref_dict START')
    logger.debug('Collecting comments from the old article (remote)')
    result = {}
    refs = bs.find_all(re.compile('ac:inline-comment-marker'))
    for ref in refs:
        ref_id = ref.attrs['ac:ref']
        try:
            full, (before, comment, after) = unwrap(ref)
        except RuntimeError:
            logger.debug("Inline comment tag has other tags inside. We can't"
                         f" process such yet, skipping:\n{ref}")
            continue
        cs = dict(full=full,
                  ref_id=ref_id,
                  before=before,
                  comment=comment,
                  after=after)

        # if 'before string' was already added to result — absorb the comment
        # dictionary instead
        if cs['before'] and id(cs['before']) in result:
            cs['before'] = result.pop(id(cs['before']))
        result[id(cs['full'])] = cs
    logger.debug(f'Collected comments:\n\n{pformat(result)}')
    logger.debug('generate_ref_dict END')
    return result


def unwrap(element):
    '''
    Unwrap an element from a tag in place. The tag must only contain one string inside.
    The string will be connected to text before and after tag.
    Function returns two elements:

    full_string, (before, element, after)

    - full_string — a full NavigableString, which replaced the tag and the text before/after;
    - A tuple of three elements:
      - before — original NavigableString, that was before the tag or None if there wasn't any.
      - element — original tag itself.
      - after — original NavigableString, that was after the tag or None if there wasn't any.
    '''
    before = after = None
    children = list(element.children)
    if len(children) > 1:
        raise RuntimeError('Tag should wrap just one string')
    if len(children) == 1 and not isinstance(children[0], NavigableString):
        raise RuntimeError('Tag should include only string')
    content = element.text
    if isinstance(element.previous_sibling, NavigableString):
        before = element.previous_sibling.extract()
        content = before + content
    if isinstance(element.next_sibling, NavigableString):
        after = element.next_sibling.extract()
        content = content + after
    ns = NavigableString(content)
    element.replace_with(ns)
    return ns, (before, element, after)


def find_place2(old_strings, new_strings: list, ref_dict: dict) -> dict:
    '''
    Compare `old_strings` and `new_strings`.
    For each element of ref_dict: Find strings in `new_strings` which correspond
    to the commented string, described by `ref_dict` element. This string is one
    of the `old_strings`.

    Return a list of tuples, each containing three elements:

    [(info_dict, indeces, equal)]

    - info_dict — an {info_dict} of the inline comment.
    - indeces — a list of indeces of the `new_strings` which correspond to the
      inline comment in the old text.
    - equal — a boolean value which tells whether the commented paragraph was changed
      or not. True — unchanged, False — changed.
    '''
    logger.debug('find_place2 START')
    result = []

    # strip all strings from indentations and formatting for comparison
    s_old_strings = [s.strip() for s in old_strings]
    s_new_strings = [s.strip() for s in new_strings]

    sm = SequenceMatcher(None, s_old_strings, s_new_strings)
    sm.ratio()
    Opcode = namedtuple('opcode', ('tag', 'a_s', 'a_e', 'b_s', 'b_e'))
    opcodes = [Opcode(*opc) for opc in sm.get_opcodes()]
    logger.debug(f'Opcodes after matching: {sm.get_opcodes()}')

    # We use IDs to determine the correct string because the tree may contain
    # strings with equal values, but located in different parts of the tree. ID
    # allows to determine the correct string precisely.
    old_string_ids = [id(s) for s in old_strings]
    for cs_id in ref_dict:
        equal = False
        ind = old_string_ids.index(cs_id)

        for i in range(len(opcodes)):
            if opcodes[i].a_s <= ind < opcodes[i].a_e:
                break
        else:
            i = None
        if i is None:
            continue

        if opcodes[i].tag == 'equal':
            indeces = [opcodes[i].b_s + (ind - opcodes[i].a_s)]
            equal = True
        elif opcodes[i].tag == 'replace':
            indeces = list(range(opcodes[i].b_s, opcodes[i].b_e))
        elif opcodes[i].tag == 'delete':
            indeces = []
            if i and opcodes[i - 1].tag == 'insert':
                indeces.extend(range(opcodes[i - 1].b_s, opcodes[i - 1].b_e))
            if i + 2 <= len(opcodes) and opcodes[i + 1].tag == 'insert':
                indeces.extend(range(opcodes[i + 1].b_s, opcodes[i + 1].b_e))
            if not indeces:
                indeces.append(opcodes[i].b_s - 1 if opcodes[i].b_s else 0)
                indeces.append(opcodes[i].b_e if opcodes[i].b_e + 1 <= len(new_strings) else opcodes[i].b_e - 1)
        result.append((ref_dict[cs_id], indeces, equal))
    logger.debug(f'List of found places:\n\n{pformat(result)}')
    logger.debug('find_place2 END')
    return result


def add_unique(a: list, b: list, at_beginning: bool = True) -> None:
    '''
    Add only unique elements from b to a in place.
    If `at_beginning` is True — elements are inserted at the beginning
    of the a list. If False — they are appended at the end.'''
    for i in b:
        if i not in a:
            if at_beginning:
                a.insert(0, i)
            else:
                a.append(i)


def correct_places(places: list, strings: list):
    '''
    Looks for strings which are inside confluence-tags <ac:... and removes such
    strings from the links (we cannot add inline comments into macros).
    In place.

    :param places:  list of tuples, got from find_place2 function:
                    [(info_dict, indeces, equal)]
    :param strings: list of NavigableStrings from the new content, which are
                    right now a part of the tree.
    '''
    logger.debug('correct_places START')
    for place in places:
        to_remove = []
        for i in range(len(place[1])):
            index = place[1][i]
            cur = strings[index]
            while cur:
                if cur.name and cur.name.startswith('ac:'):
                    logger.debug(f"string '{strings[index]}' is inside macro {cur.name}"
                                 " and will be removed")
                    to_remove.append(i)
                    break
                cur = cur.parent
        for i in reversed(to_remove):
            s = place[1].pop(i)
            logger.debug(f"Removed string [{s}]: '{strings[s]}'")
    logger.debug('correct_places END')


def divide_places(places: list) -> dict:
    '''
    Takes a list of tuples, got from find_place2 function:
    [(info_dict, indeces, equal)]

    Looks for the places with equal == True and gathers them into a separate list.
    Removes all indeces which were mentioned in `equal` places from other places.
    Gathers references in the correct order from the remaining places and saves them
    in a dictionary with key = string index, value = list of ref_ids, which point
    to this string.

    Returns a tuple with two items:

    (equal, not_equal)

    - equal = [(info_dict, indeces, equal)] : list of equal places;
    - not_equal = {index: [ref_list]} : dictionary with references for strings
                which are not equal.
    '''
    logger.debug('divide_places START')

    equal_places = [(info_dict, copy(indeces), equal)
                    for info_dict, indeces, equal in places if equal]

    # remove all places where equal strings are mentioned
    for _, equal_indeces, _ in equal_places:
        for _, indeces, _ in places:
            equal_index = equal_indeces[0]
            if equal_index in indeces:
                indeces.pop(indeces.index(equal_index))

    # remove all places where strings are empty after prev. stage
    places = [p for p in places if p[1]]

    def get_refs(info_dict: dict) -> list:
        '''Get all ref_ids from a nested place in the correct order'''
        refs = [info_dict['ref_id']]
        if isinstance(info_dict['before'], dict):
            add_unique(refs, get_refs(info_dict['before']))
        return refs

    # make a dictionary with refs list for each string index
    unequal = {}
    for info_dict, indeces, _ in places:
        refs = get_refs(info_dict)
        for pos in indeces:
            add_unique(unequal.setdefault(pos, []), refs, False)

    logger.debug(f'Equal places:\n\n{pformat(equal_places)}\n\n'
                 f'References for changed strings:\n\n{pformat(unequal)}')
    logger.debug('divide_places END')
    return equal_places, unequal


def restore_equal_refs(places: list, new_strings: list) -> None:
    """
    Receive a list of `place` tuples and a list of strings of the new tree `new_strings`:

    places = [(info_dict, indeces, equal)]
    new_strings = [NavigableString]

    Restore the inline comments in corresponding strings of new_strings (determined
    by place[1]) in the same way it was present in the old string. The way is
    determined by the `place` tuple.

    Function returns nothing, the comments are restored in place.
    """
    def get_content_list(ref_dict: dict) -> list:
        '''
        Get consequetive list of html elements and strings in the correct order
        to be inserted instead of the target string.
        '''
        content = []
        if isinstance(ref_dict['before'], dict):
            content.extend(get_content_list(ref_dict['before']))
        elif ref_dict['before'] is not None:
            content.append(ref_dict['before'])
        content.append(ref_dict['comment'])
        # if isinstance(ref_dict['after'], dict):
        #     content.extend(get_content_list(ref_dict['after']))
        if ref_dict['after'] is not None:
            content.append(ref_dict['after'])
        return content

    logger.debug('restore_equal_refs START')

    for info_dict, indeces, _ in places:
        logger.debug(f'Source info_dict:\n\n{pformat(info_dict)}')

        content_list = get_content_list(info_dict)

        logger.debug(f'Content list to insert:\n\n{pformat(content_list)}')

        target = new_strings[indeces[0]]

        logger.debug(f'String to be replaced: {target}')

        # we use copy to detach element from previous tree
        new_elem = copy(content_list[0])
        target.replace_with(new_elem)
        target = new_elem
        for i in range(1, len(content_list)):
            new_elem = copy(content_list[i])
            target.insert_after(new_elem)
            target = new_elem

    logger.debug('restore_equal_refs END')


def insert_unequal_refs(unequal: dict, new_strings: list, resolved_ids: list):
    '''
    Receive an `unequal` dictionary with ref_ids and a list of strings of the
    new tree `new_strings`:

    unequal = {index: [list_of_ref_ids]}
    new_strings = [NavigableString]
    resolved_ids = [resolved_ref_ids]

    Wrap each NavigableString determined by index from `unequal` dictionary in
    the corresponding inline-comment tag from the dict value. If the value
    contains several ref_ids — divide the string into equal chunks of text for
    each ref_id. If one or more of these several ref_ids are resolved — they are
    filtered out for better output. They will be removed from the source.

    Function returns nothing, the comments are restored in place.
    '''
    logger.debug('insert_unequal_refs START')
    for pos, refs in unequal.items():
        logger.debug(f'Inserting refs into string #{pos}')
        if len(refs) > 1:
            logger.debug('More than one ref claim for this string.'
                         'Leaving out resolved: '
                         f'{[ref for ref in refs if ref in resolved_ids]}')
            refs = [ref for ref in refs if ref not in resolved_ids]
            if not refs:
                logger.debug('All refs for the string were resolved. Skipping')
                continue

        logger.debug(f'Refs to insert: {refs}')

        contents = []
        ns = new_strings[pos]

        logger.debug(f'String to be replaced: {ns}')

        # if number of refs more than chars in string — ignore the rest
        num_refs = min(len(refs), len(ns))
        chunk_size = len(ns) // num_refs

        logger.debug(f'Dividing string equally into {num_refs} chunks by {chunk_size} chars.')

        for i in range(num_refs):
            tag = Tag(name='ac:inline-comment-marker',
                      attrs={'ac:ref': refs[i]})
            start = i * chunk_size
            end = start + chunk_size if i != num_refs - 1 else None
            tag.string = ns[start:end]
            contents.append(tag)

        ns.replace_with(contents[0])
        target = contents[0]
        for i in range(1, len(contents)):
            target.insert_after(contents[i])
            target = contents[i]

    logger.debug('insert_unequal_refs END')
