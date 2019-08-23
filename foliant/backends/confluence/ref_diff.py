import re

from difflib import SequenceMatcher
from collections import namedtuple


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
    # print('first', first, opcodes[first])
    # print('last', last, opcodes[last])
    if first == last:
        if opcodes[last].tag == 'delete':
            if opcodes[last + 1].tag == 'insert':
                new_start = opcodes[first].b_s
                new_end = opcodes[first + 1].b_e
                # print(1)
                return new_start, new_end
            else:
                new_start = opcodes[first].b_s
                new_end = opcodes[first].b_s + 5
                return new_start, new_end
        elif opcodes[last].tag == 'replace':
            # print(3)
            return opcodes[last].b_s, opcodes[last].b_e
        else:  # opcodes[last].tag == 'equal'
            new_start = opcodes[first].b_s + (start - opcodes[first].a_s)
            new_end = new_start + (end - start)
            # print(4)
            return new_start, new_end
    else:  # first != last
        if opcodes[first].tag in ('delete', 'replace'):
            # print(5)
            new_start = opcodes[first].b_s
        else:  # equal
            # print(6)
            new_start = (start - opcodes[first].a_s) + opcodes[first].b_s
        if opcodes[last].tag == 'delete':
            if opcodes[last + 1].tag == 'insert':
                # print(7)
                new_end = opcodes[last + 1].b_e
            else:
                # print(8)
                new_end = opcodes[last].b_e
        elif opcodes[last].tag == 'replace':
            # print(9)
            new_end = opcodes[last].b_e
        else:  # equal
            # print(10)
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
