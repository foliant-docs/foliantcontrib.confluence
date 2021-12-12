import re
import yaml

from logging import getLogger
from pathlib import PosixPath

from bs4 import BeautifulSoup
from pyparsing import CharsNotIn
from pyparsing import Group
from pyparsing import Literal
from pyparsing import OneOrMore
from pyparsing import StringEnd
from pyparsing import StringStart
from pyparsing import Suppress
from pyparsing import Word
from pyparsing import ZeroOrMore
from pyparsing import nums
from pyparsing import oneOf

from foliant.contrib.combined_options import CombinedOptions

logger = getLogger('flt.confluence_final')

FENCE_BLOCKS_RE = re.compile(
    r'(?:^|\n)(?P<backticks>```|~~~)'
    r'(?:[ \t]*(?P<syntax>\w+)[ \t]*)?'
    r'(?:\n)(?P<content>[\s\S]+?)'
    r'(?P=backticks)'
)

PRE_BLOCKS_RE = re.compile(
    r'(?:^|\n\n)(?P<content>(?:    [^\n]*\n)+)'
)
SYNTAX_CONVERT = {
    'python': 'py',
    'actionscript': 'actionscript3',
    'applescript': 'applescript',
    'bash': 'bash',
    'c#': 'c#',
    'cs': 'c#',
    'c': 'c',
    'cpp': 'cpp',
    'css': 'css',
    'coldfusion': 'coldfusion',
    'delphi': 'delphi',
    'diff': 'diff',
    'erlang': 'erl',
    'groovy': 'groovy',
    'xml': 'xml',
    'html': 'html',
    'java': 'java',
    'js': 'js',
    'javascript': 'javascript',
    'php': 'php',
    'perl': 'perl',
    'powershell': 'powershell',
    'yaml': 'yml'
}

THEMES = ['emacs', 'django', 'fadetogrey', 'midnight', 'rdark', 'eclipse', 'confluence']


def process_code_blocks(content: str, config: dict, chapter=None) -> str:
    def sub_block(match) -> str:
        if chapter:
            meta = chapter.get_section_by_offset(match.start())
            meta_config = meta.data.get('confluence', {}).get('codeblocks', {})
            options = CombinedOptions(
                {
                    'backend': config,
                    'meta': meta_config
                },
                priority='meta'
            )
        else:
            options = config

        language = None
        if 'syntax' in match.groupdict():
            language = match.group('syntax')

        source = match.group('content')
        if source.endswith('\n'):
            source = source[:-1]
        logger.debug(f'Found code block ({language}):\n{source[:150]}\n...')
        return gen_code_macro(source,
                              language=language,
                              theme=options.get('theme'),
                              title=options.get('title'),
                              linenumbers=options.get('linenumbers'),
                              collapse=options.get('collapse'))

    logger.debug('Normalizing document')
    result = _normalize(content)

    logger.debug('Processing fence blocks')
    result = FENCE_BLOCKS_RE.sub(sub_block, result)

    # logger.debug('Processing pre blocks')
    # result = PRE_BLOCKS_RE.sub(sub_block, result)
    return result


def _normalize(markdown_content: str) -> str:
    '''Normalize the source Markdown content to simplify
    further operations: replace ``CRLF`` with ``LF``,
    remove excessive whitespace characters,
    provide trailing newline, etc.
    :param markdown_content: Source Markdown content
    :returns: Normalized Markdown content
    '''

    markdown_content = re.sub(r'\r\n', '\n', markdown_content)
    markdown_content = re.sub(r'\r', '\n', markdown_content)
    markdown_content = re.sub(r'(?<=\S)$', '\n', markdown_content)
    markdown_content = re.sub(r'\t', '    ', markdown_content)
    markdown_content = re.sub(r'[ \n]+$', '\n', markdown_content)
    markdown_content = re.sub(r' +\n', '\n', markdown_content)

    return markdown_content


def gen_code_macro(source: str,
                   language: str or None = None,
                   theme: str or None = None,
                   title: str or None = None,
                   linenumbers: bool = False,
                   collapse: bool = False):
    result = '<raw_confluence><p><ac:structured-macro ac:name="code" ac:schema-version="1">\n'
    if language and language.lower() in SYNTAX_CONVERT:
        result += f'  <ac:parameter ac:name="language">{SYNTAX_CONVERT[language.lower()]}</ac:parameter>\n'
    if theme and theme.lower() in THEMES:
        result += f'  <ac:parameter ac:name="theme">{theme.lower()}</ac:parameter>\n'
    if title:
        result += f'  <ac:parameter ac:name="title">{title}</ac:parameter>\n'
    if linenumbers:
        result += '  <ac:parameter ac:name="linenumbers">true</ac:parameter>\n'
    if collapse:
        result += '  <ac:parameter ac:name="collapse">true</ac:parameter>\n'
    result += f'<ac:plain-text-body><![CDATA[{source}]]></ac:plain-text-body>\n</ac:structured-macro></p></raw_confluence>'
    return result


def process_task_lists(content: str) -> str:
    item = Group(CharsNotIn('\n') + (StringEnd() | '\n')).leaveWhitespace()
    checkbox = oneOf(['[ ]', '[x]'])
    marker = Suppress(oneOf(['+', '-', '*']) | Word(nums) + '.')
    #
    indent = oneOf(['    ', '\t']).leaveWhitespace()
    indents = Group(ZeroOrMore(indent))
    #
    list_item = Group(indents + marker + checkbox + item)
    #
    before = Suppress(StringStart() | Literal('\n\n')).leaveWhitespace()
    list_ = before + OneOrMore(list_item)
    #
    list_.setParseAction(replace_list)
    return list_.transformString(content)


def replace_list(match):
    tasklist = TaskList()
    for tabs, chk, item in match:
        tasklist.add_item(
            item[0].strip(),
            chk == '[x]',
            len(tabs)
        )
    return f'<raw_confluence>{tasklist.to_string()}</raw_confluence>'


class Task:
    def __init__(self, text: str, checked: bool, id_: int):
        self.text = text
        self.status = 'complete' if checked else 'incomplete'
        self.children = []
        self.id = id_

    def __repr__(self):
        return f'Task({self.text}, {self.status})'

    def to_string(self):
        result = f'''
<ac:task>
    <ac:task-id>{self.id}</ac:task-id>
    <ac:task-status>{self.status}</ac:task-status>
    <ac:task-body>
        <span class="placeholder-inline-tasks">{self.text}</span>'''

        for child in self.children:
            result += '''
        <ac:task-list>'''
            result += child.to_string()
            result += '''
        </ac:task-list>'''

        result += '''
    </ac:task-body>
</ac:task>'''
        return result


class TaskList:
    def __init__(self):
        self.tasks = []
        self.last_id = 0

    def add_item(self, text: str, checked: bool, level: int = 0):
        cur_level = 0
        cur_list = self.tasks
        while cur_level < level:
            cur_list = cur_list[-1].children
            if cur_list:
                cur_level += 1
            else:
                break
        self.last_id += 1
        cur_list.append(Task(text, checked, self.last_id))

    def __repr__(self):
        return f'TaskList({", ".join((str(t) for t in self.tasks))})'

    def to_string(self):
        result = '<ac:task-list>\n'
        for task in self.tasks:
            result += task.to_string()
        result += '\n</ac:task-list>\n'
        return result


def convert_image(tag: str, current_filepath: PosixPath) -> str:
    '''
    If ac:image tag references local image, make its path absolute.

    :param tag: ac:image original tag
    :param current_filepath: path to Markdown file where this tag was encountered.

    :returns: modified ac:image tag with absolute path to the local image.
    '''
    logger.debug(f'Parsing confluence image: {tag}')
    root = BeautifulSoup(tag, 'html.parser')
    ac_image = root.find('ac:image')
    if not ac_image:
        logger.debug(f'ac:image tag not found, skipping image')
        return tag

    ri_attachment = ac_image.find('ri:attachment')
    if not ri_attachment:
        logger.debug(f'ri:attachment tag not found, skipping image')
        return tag

    # using yaml to allow !project_path !path tags
    rel_path = yaml.load(ri_attachment.get('ri:filename'), yaml.Loader)
    if not rel_path:
        logger.debug(f'ri:filename attribute is not preset, skipping image')
        return tag
    src = (current_filepath.parent / rel_path).resolve()
    if not src.exists():
        logger.debug(f'{src} does not exist, returning content as is')
        return tag
    logger.debug(f'got local path to image: {src}')

    ri_attachment['ri:filename'] = src

    return str(root)


def convert_attachment(tag: str, current_filepath: PosixPath) -> str:
    '''
    If ac:link tag references local attachment, make its path absolute.

    :param tag: ac:link original tag
    :param current_filepath: path to Markdown file where this tag was encountered.

    :returns: modified ac:link tag with absolute path to the local image.
    '''
    logger.debug(f'Parsing confluence link to attachment: {tag}')
    root = BeautifulSoup(tag, 'html.parser')
    ac_link = root.find('ac:link')
    if not ac_link:
        logger.debug(f'ac:link tag not found, skipping')
        return tag

    ri_attachment = ac_link.find('ri:attachment')
    if not ri_attachment:
        logger.debug(f'ri:attachment tag not found, skipping')
        return tag

    # using yaml to allow !project_path !path tags
    rel_path = yaml.load(ri_attachment.get('ri:filename'), yaml.Loader)
    if not rel_path:
        logger.debug(f'ri:filename attribute is not preset, skipping')
        return tag
    src = (current_filepath.parent / rel_path).resolve()
    if not src.exists():
        logger.debug(f'{src} does not exist, returning content as is')
        return tag
    logger.debug(f'got local path to attachment: {src}')

    ri_attachment['ri:filename'] = src

    return str(root)
