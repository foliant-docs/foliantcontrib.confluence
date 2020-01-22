from setuptools import setup


SHORT_DESCRIPTION = 'Confluence backend for Foliant documentation generator.'

try:
    with open('README.md', encoding='utf8') as readme:
        LONG_DESCRIPTION = readme.read()

except FileNotFoundError:
    LONG_DESCRIPTION = SHORT_DESCRIPTION


setup(
    name='foliantcontrib.confluence',
    description=SHORT_DESCRIPTION,
    long_description=LONG_DESCRIPTION,
    long_description_content_type='text/markdown',
    version='0.6.5',
    author='Daniil Minukhin',
    author_email='ddddsa@gmail.com',
    url='https://github.com/foliant-docs/foliantcontrib.confluence',
    packages=['foliant.backends.confluence', 'foliant.preprocessors'],
    license='MIT',
    platforms='any',
    install_requires=[
        'foliant>=1.0.8',
        'atlassian-python-api',
        'foliantcontrib.utils.combined_options>=1.0.6',
        'foliantcontrib.utils.preprocessor_ext>=1.0.2',
        'foliantcontrib.flatten>=1.0.5',
        'foliantcontrib.meta>=1.2.0',
        'beautifulsoup4',
    ],
    classifiers=[
        "Development Status :: 5 - Production/Stable",
        "Environment :: Console",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Programming Language :: Python",
        "Topic :: Documentation",
        "Topic :: Utilities",
    ]
)
