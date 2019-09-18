import re

from copy import copy
from difflib import SequenceMatcher
from collections import namedtuple

from bs4 import BeautifulSoup, NavigableString, Tag


def restore_refs(old_content: str, new_content: str, resolve_changed: bool = False):
    old_bs = BeautifulSoup(old_content, 'html.parser')
    new_bs = BeautifulSoup(new_content, 'html.parser')
    ref_dict = get_original_ref_dict(old_bs)
    new_strings = [s for s in new_bs.strings if s.strip()]
    old_strings = [s for s in old_bs.strings if s.strip()]
    places = find_place2(old_strings, new_strings, ref_dict)
    c_places = correct_places(places)
    for place in c_places['equal']:
        restore_equal_ref(place, new_strings)
    if not resolve_changed:
        for pos, refs in c_places['shared'].items():
            insert_shared_refs(pos, refs, new_strings)
    return str(new_bs)


def unwrap(element):
    parent = element.parent
    orig = dict(before=None, comment=element, after=None)
    children = list(element.children)
    if len(children) > 1:
        raise RuntimeError('Tag should wrap just one string')
    if len(children) == 1 and not isinstance(children[0], NavigableString):
        raise RuntimeError('Tag should include only string')
    content = element.text
    siblings = parent.contents
    ind = siblings.index(element)
    if ind > 0 and isinstance(siblings[ind - 1], NavigableString):
        content = siblings[ind - 1] + content
        orig['before'] = siblings[ind - 1]
        siblings.pop(ind - 1)
        ind -= 1
    if ind < len(siblings) - 1 and isinstance(siblings[ind + 1], NavigableString):
        content = content + siblings[ind + 1]
        orig['after'] = siblings[ind + 1]
        siblings.pop(ind + 1)
    ns = NavigableString(content)
    element.replace_with(ns)
    return ns, orig


def get_original_ref_dict(bs: BeautifulSoup) -> dict:
    result = {}
    refs = bs.find_all(re.compile('ac:inline-comment-marker'))
    for ref in refs:
        ref_id = ref.attrs['ac:ref']
        full, compound_dict = unwrap(ref)
        cs = dict(full=full, ref_id=ref_id, **compound_dict)
        if cs['before'] and id(cs['before']) in result:
            cs['before'] = result.pop(id(cs['before']))
        if cs['after'] and id(cs['after']) in result:
            cs['after'] = result.pop(id(cs['after']))
        result[id(cs['full'])] = cs
    return result


def find_place2(old_strings, new_strings: list, strings: dict) -> dict:
    result = []
    s_old_strings = [s.strip() for s in old_strings]
    s_new_strings = [s.strip() for s in new_strings]
    sm = SequenceMatcher(None, s_old_strings, s_new_strings)
    sm.ratio()
    Opcode = namedtuple('opcode', ('tag', 'a_s', 'a_e', 'b_s', 'b_e'))
    opcodes = [Opcode(*opc) for opc in sm.get_opcodes()]
    old_string_ids = [id(s) for s in old_strings]
    for cs_id in strings:
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
            found = [opcodes[i].b_s + (ind - opcodes[i].a_s)]
            equal = True
        elif opcodes[i].tag == 'replace':
            found = list(range(opcodes[i].b_s, opcodes[i].b_e))
        elif opcodes[i].tag == 'delete':
            found = []
            if i and opcodes[i - 1].tag == 'insert':
                found.extend(range(opcodes[i - 1].b_s, opcodes[i - 1].b_e))
            if i + 2 <= len(opcodes) and opcodes[i + 1].tag == 'insert':
                found.extend(range(opcodes[i + 1].b_s, opcodes[i + 1].b_e))
            if not found:
                found.append(opcodes[i].b_s - 1 if opcodes[i].b_s else 0)
                found.append(opcodes[i].b_e if opcodes[i].b_e + 1 <= len(new_strings) else opcodes[i].b_e - 1)
        result.append((strings[cs_id], found, equal))
    return result


def correct_places(places: list) -> list:
    equal_places = [(p[0], copy(p[1]), p[2]) for p in places if p[2]]
    #
    # remove all places where equal strings are mentioned
    for ep in equal_places:
        for place in places:
            if ep[1][0] in place[1]:
                place[1].pop(place[1].index(ep[1][0]))
    #
    # remove all places where strings are empty after prev. stage
    places = [p for p in places if p[1]]
    #
    # make a list with refs which share the same string
    def get_refs(ref_dict: dict) -> list:
        refs = {ref_dict['ref_id']}
        if isinstance(ref_dict['before'], dict):
            refs.update(get_refs(ref_dict['before']))
        if isinstance(ref_dict['after'], dict):
            refs.update(get_refs(ref_dict['after']))
        return refs
    shared_places = {}
    for place in places:
        refs = get_refs(place[0])
        for pos in place[1]:
            shared_places.setdefault(pos, set()).update(refs)
    # for place in places:
    #     for pos in place[1]:
    #         refs = {place[0]['ref_id']}
    #         for place2 in places:
    #             if place2 is place:
    #                 continue
    #             if pos in place2[1]:
    #                 refs.update(get_refs(place2))
    #                 place2[1].pop(place2[1].index(pos))
    #         if len(refs) > 1:
    #             shared_places[pos] = refs
    #
    # remove all places where strings are empty after prev. stage
    # single_places = [p for p in places if p[1]]
    return {'equal': equal_places,
            'shared': shared_places}
            # 'single': single_places}


def restore_equal_ref(place: tuple, new_strings: list):
    """
    for place in cp['equal']:
        restore_equal_ref(place, bns)
    """
    def get_content_list(ref_dict: dict) -> list:
        content = []
        if isinstance(ref_dict['before'], dict):
            content.extend(get_content_list(ref_dict['before']))
        elif ref_dict['before'] is not None:
            content.append(ref_dict['before'])
        content.append(ref_dict['comment'])
        if isinstance(ref_dict['after'], dict):
            content.extend(get_content_list(ref_dict['after']))
        elif ref_dict['after'] is not None:
            content.append(ref_dict['after'])
        return content
    content_list = get_content_list(place[0])
    target = new_strings[place[1][0]]
    new_elem = copy(content_list[0])
    target.replace_with(new_elem)
    target = new_elem
    for i in range(1, len(content_list)):
        new_elem = copy(content_list[i])
        target.insert_after(new_elem)
        target = new_elem


def insert_shared_refs(pos: int, refs: set, new_strings: list):
    contents = []
    refs_list = list(refs)
    ns = new_strings[pos]
    # if number of refs more than chars in string — ignore the rest
    num_refs = len(refs_list) if len(refs_list) <= len(ns) else len(ns)
    num_chars = len(ns) // num_refs
    for i in range(num_refs):
        tag = Tag(name='ac:inline-comment-marker',
                  attrs={'ac:ref': refs_list[i]})
        start = i * num_chars
        tag.string = ns[start:start + num_chars]
        contents.append(tag)
    #
    ns.replace_with(contents[0])
    target = contents[0]
    for i in range(1, len(contents)):
        target.insert_after(contents[i])
        target = contents[i]

# def insert_single_ref(pos: int, place, new_)



def is_inside_tag(source: str, position: int):
    '''
    Determine if position of the source is inside an html-tag.
    If it is — returns a tuple with tag boundries,
    if it's not — returns None
    '''

    gt = source.find('>', position)
    lt = source.find('<', position)
    if gt == -1 or lt < gt:
        return  # not inside tag
    elif lt == -1 or lt > gt:
        end = gt + 1
        cur = position
        while True:
            cur -= 1
            if source[cur] == '<':
                return cur, end
            elif source[cur] == '>' or cur == 0:
                return  # something wrong, that's not a tag


def cut_out_tag_fragment(source: str, start: int, end: int):
    '''
    Determine if part of the source, limited by start and end indeces,
    contains a fragment of a tag. If it does — cut out the tag part and return
    the new indeces.
    '''
    new_start = start
    new_end = end
    span = is_inside_tag(source, start)
    if span:
        new_start = span[1]
        if new_start >= end:
            for i in range(10):
                new_end = new_start + i
                if source[new_end] == '<':  # another tag starts
                    break
    span = is_inside_tag(source, end)
    if span:
        new_end = span[0]
        if new_start >= new_end:
            for i in range(10):
                new_start = new_end - i
                if source[new_start] == '>':
                    new_start += 1
                    break
    return new_start, new_end


def fix_refs(refs: [(str, int, int)]) -> [(str, int, int)]:
    # removing dublicates
    new_refs = list(dict.fromkeys(refs))
    # new_refs.sort(key=lambda x: (x[0], x[1]))
    return new_refs


def find_place(old: str, new: str, start: int, end: int) -> (int, int):
    '''
    Given the position of the fragment of the old text defined by start and
    end indeces, try to determine its position in the new, potentially changed
    text.

    Return a tuple (new_start, new_end)
    '''
    sm = SequenceMatcher(None, old, new)
    sm.ratio()
    Opcode = namedtuple('opcode', ('tag', 'a_s', 'a_e', 'b_s', 'b_e'))
    opcodes = [Opcode(*opc) for opc in sm.get_opcodes()]
    # print(opcodes)
    first = last = None
    for i in range(len(opcodes)):
        if opcodes[i].a_s <= start and opcodes[i].a_e > start:
            first = i  # opcode index which features the start point
            break
    for i in range(len(opcodes)):
        if opcodes[i].a_s < end and opcodes[i].a_e >= end:
            last = i  # opcode index which features the end point
            break
    print('first', first, opcodes[first])
    print('last', last, opcodes[last])
    if first == last:
        if opcodes[last].tag == 'delete':
            if len(opcodes) - 1 >= last + 1 and opcodes[last + 1].tag == 'insert':
                new_start = opcodes[first].b_s
                new_end = opcodes[first + 1].b_e
                print(1)
                return new_start, new_end
            else:
                new_start = opcodes[first].b_s - 10
                # if opcodes[first].b_s < len(new) - 1:
                    # the fragment was in the middle of the document
                new_end = opcodes[first].b_s + 10
                # else:
                #     # the fragment was in the end. Select some chars before
                #     new_end = new_start
                #     new_start -= 10
                return new_start, new_end
        elif opcodes[last].tag == 'replace':
            print(3)
            return opcodes[last].b_s, opcodes[last].b_e
        else:  # opcodes[last].tag == 'equal'
            new_start = opcodes[first].b_s + (start - opcodes[first].a_s)
            new_end = new_start + (end - start)
            print(4)
            return new_start, new_end
    else:  # first != last
        if opcodes[first].tag in ('delete', 'replace'):
            print(5)
            new_start = opcodes[first].b_s
        else:  # equal
            print(6)
            new_start = (start - opcodes[first].a_s) + opcodes[first].b_s
        if opcodes[last].tag == 'delete':
            if opcodes[last + 1].tag == 'insert':
                print(7)
                new_end = opcodes[last + 1].b_e
            else:
                print(8)
                new_end = opcodes[last].b_e
        elif opcodes[last].tag == 'replace':
            print(9)
            new_end = opcodes[last].b_e
        else:  # equal
            print(10)
            new_end = opcodes[last].b_e - (opcodes[last].a_e - end)
        return new_start, new_end


def add_ref(ref_id: str, text: str) -> str:
    # print(f'working on ref {ref_id}')
    ref_open = '<ac:inline-comment-marker ac:ref="{}">'.format(ref_id)
    ref_close = '</ac:inline-comment-marker>'
    # print('text:', text)
    # p_tag = r'<(?P<close>/?)(?P<tag>[\w:-]+?)\s*[^/>]+>'
    p_tag = r'<(?P<close>/?)(?P<tag>[^\s/>]+)[^/]*?>'
    opened = []
    unopened = []
    for m in re.finditer(p_tag, text):
        if m.group('close'):
            if opened:
                opened.pop()
            else:
                unopened.append(m)
        else:
            opened.append(m)
    result = ref_open
    if unopened:
        for i in range(len(unopened)):
            if i == 0:
                result += text[:unopened[0].start()]
            else:
                result += text[unopened[i - 1].end():unopened[i].start()]
            result += ref_close + unopened[i].group(0) + ref_open
        result += text[unopened[i].end():]
    else:
        result += text
    if opened:
        # print('opened:', opened)
        for m in reversed(opened):
            # print(m.group('tag'))
            result += '</{}>'.format(m.group('tag'))
        result += ref_close
        for m in opened:
            result += m.group(0)
    else:
        result += ref_close
    return result
