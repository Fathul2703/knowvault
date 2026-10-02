# Engineering Onboarding Guide

Welcome to the engineering team. This guide lists what to do in your first two weeks.

## First day

You receive a laptop with the operating system already installed. Enable full-disk encryption
before you sign in to any company system. Your manager assigns you an onboarding buddy who
answers questions during the first month.

## Accounts and access

Request access to the code repository, the issue tracker and the chat workspace through the
access portal. Production access is not granted in the first two weeks; you get read-only
access to staging instead. Hardware security keys are mandatory for the code repository, and
two keys are issued to every engineer so one can be kept as a spare.

## Development setup

Clone the main repository and run the setup script, which installs the pinned toolchain. The
whole test suite should pass on a fresh machine in under ten minutes. If it does not, report it
in the developer experience channel; a slow or flaky setup is treated as a bug.

## Your first change

Pick an issue labelled good-first-issue. Every change needs one approving review and green
continuous integration before it is merged. Small pull requests are preferred: aim for fewer
than 400 changed lines so the reviewer can read everything carefully.

## Learning the product

Spend at least one afternoon with the support team in your first week. Listening to real
customer problems is the fastest way to understand which parts of the product matter most.
