# Cohesion compiler for AWS Serverless Workflows

Cohesion is a source-to-source compiler that accepts a Python program
and outputs an AWS Step Functions workflow plus a set of Lambda
functions. While AWS is the only supported target, most of the code is
AWS-independent, so backends for other serverless systems can be
built.

Cohesion supports a subset of Python, and adds a small amount of
syntax.

It's aimed primarily as a way to make it easier to produce new
serverless systems; not as a way to transparently transform large
existing codebases.

See [preview.cohesion.dev](https://preview.cohesion.dev) for a
web-based demo of some of its features.

## How to run

```
cd src

make venv
. ./venv/bin/activate

make compiler_tests

./coco --help
```

## Questions? Comments?

I'd love to chat! I'm [@soamv](https://twitter.com/soamv) on twitter,
or send me email (`contact@soam.dev`).
