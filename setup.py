"""Sets up the parameters required by PyPI"""
from pathlib import Path
from setuptools import setup, find_packages

this_directory = Path(__file__).parent
long_description = (this_directory / 'README.md').read_text()

setup(
    name='mkdocs-live-edit-plugin',
    version='0.1.2',
    description='An MkDocs plugin that allows editing pages directly from the browser.',
    long_description=long_description,
    long_description_content_type='text/markdown',
    keywords='mkdocs python markdown editing authoring wiki server',
    url='https://github.com/eddyluten/mkdocs-live-edit-plugin',
    author='Eddy Luten',
    author_email='eddyluten@gmail.com',
    license='MIT',
    python_requires='>=3.10',
    install_requires=[
        'mkdocs',
        'websockets',
    ],
    classifiers=[
        'License :: OSI Approved :: MIT License',
        'Programming Language :: Python',
        'Programming Language :: Python :: 3 :: Only',
        'Topic :: Software Development :: Libraries :: Python Modules',
    ],
    packages=find_packages(exclude=['*.tests']),
    entry_points={
        'mkdocs.plugins': ['live-edit = live.plugin:LiveEditPlugin']
    },
    data_files=[('live', ['live/live-edit.js', 'live/live-edit.css'])],
    include_package_data=True,
)
