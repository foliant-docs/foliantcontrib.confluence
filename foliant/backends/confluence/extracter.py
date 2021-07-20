'''Collection of functions to extract the foliant section from
confluence page source'''

import re

from bs4 import BeautifulSoup

OPEN_TAGS = ('foliant', 'foliant_start')
CLOSE_TAGS = ('foliant_end', 'foliant_finish', 'foliant_close')


def extract(source: str) -> (str, str, str):
    '''
    Separate the confluence page source into three parts:

    1. The code before foliant opening tag.
    2. The code inside foliant tags.
    3. The code after foliant closing tag.

    Return the tuple with these parts. Foliant tags not included.
    '''
    b = BeautifulSoup(source, 'html.parser')
    open_anchor, close_anchor = detect_foliant_blocks(b)
    before = foliant = after = None
    if open_anchor and close_anchor:
        before = get_content_before_tag(open_anchor)
        foliant = get_content_between_two_tags(open_anchor, close_anchor)
        after = get_content_after_tag(close_anchor)
    elif open_anchor:
        before = get_content_before_tag(open_anchor)
        foliant = ''
        after = get_content_after_tag(open_anchor)
        return before, '', after
    else:
        before = after = ''
        foliant = str(b)
    return before, foliant, after


def get_top_parent(element, root):
    '''Get and return closest to root parent of the element'''
    parent = element
    while parent.parent != root:
        parent = parent.parent
        if parent is None:
            return
    return parent


def get_content_between_two_tags(tag1, tag2) -> str:
    '''
    Get HTML-code between `tag1` and `tag2` and return it as string.
    Tags not included.
    '''
    ns = tag1.next_sibling
    result = ''
    while ns is not None and ns != tag2:
        result += str(ns)
        ns = ns.next_sibling
    return result


def get_content_before_tag(tag, include_tag=False) -> str:
    '''
    Get HTML-code before `tag` and return it as string.
    Tag's not included by default.
    '''
    result = ''
    bs = tag.previous_sibling
    while bs is not None:
        result = str(bs) + result
        bs = bs.previous_sibling
    return str(tag) + result if include_tag else result


def get_content_after_tag(tag, include_tag=False) -> str:
    '''
    Get HTML-code after `tag` and return it as string.
    Tag's not included by default.
    '''
    result = ''
    ns = tag.next_sibling
    while ns is not None:
        result = result + str(ns)
        ns = ns.next_sibling
    return result + str(tag) if include_tag else result


def detect_foliant_blocks(soup: BeautifulSoup) -> tuple:
    '''
    Search the `soup` tree for foliant opening and closing tags.
    Return the tuple with the topmost parents of them.
    '''
    def get_anchor_name(element):
        for child in element.children:
            if child.name == 'ac:parameter':
                return child.text.lower()
        return None
    macros = soup.find_all(re.compile('ac:structured-macro'))
    open_anchor = close_anchor = None
    for macro in macros:
        if not open_anchor and get_anchor_name(macro) in OPEN_TAGS:
            open_anchor = macro
        elif get_anchor_name(macro) in CLOSE_TAGS:
            close_anchor = macro
            break
    top_open = get_top_parent(open_anchor, soup) if open_anchor else None
    top_close = get_top_parent(close_anchor, soup) if close_anchor else None
    if top_open == top_close:
        top_close = None
    return top_open, top_close
