from setuptools import setup

setup(
    name='sonic-linecardsyncd',
    version='1.0',
    description='Linecard daemon for SONiC OTN',
    license='Apache 2.0',
    author='SONiC OTN Team',
    author_email='lu.mao@molex.com',
    url='https://github.com/Azure/sonic-platform-daemons',
    maintainer='Lu Mao',
    maintainer_email='lu.mao@molex.com',
    packages=[
        'tests'
    ],
    scripts=[
        'scripts/linecardsyncd'
    ],
    setup_requires=[
        'pytest-runner',
        'wheel'
    ],
    tests_require=[
        'pytest',
        'mock>=2.0.0',
        'pytest-cov',
        'sonic-platform-common'
    ],
    classifiers=[
        'Development Status :: 4 - Beta',
        'Environment :: No Input/Output (Daemon)',
        'Intended Audience :: Developers',
        'Intended Audience :: Information Technology',
        'Intended Audience :: System Administrators',
        'License :: OSI Approved :: Apache Software License',
        'Natural Language :: English',
        'Operating System :: POSIX :: Linux',
        'Topic :: System :: Hardware',
    ],
    keywords='sonic SONiC linecard Linecard daemon linecardsyncd',
    test_suite='setup.get_test_suite'
)
