# Reviewer rubric: Testing

Judge whether the target explains how this repository establishes correctness and how contributors should verify changes.

Look specifically for:

1. Verification strategy
- Are the principal test levels/categories understandable?
- Is their role differentiated?

2. Test organization
- Is it clear where and how tests are organized?

3. Setup and infrastructure
Where relevant, are:
- fixtures;
- factories;
- mocks/fakes;
- isolation;
- databases/services;
explained sufficiently?

4. Practical execution
- Are important test/validation commands clear?
- Is CI-triggered verification described where present?

5. Change-to-test mapping
- Does the artifact help engineers understand what kind of tests should accompany different changes?

6. Specialized testing
Where present, are significant:
- integration;
- E2E;
- contract;
- visual;
- accessibility;
- performance;
- security;
testing approaches described?

7. Testing vs Business Logic
Flag attempts to recreate complete domain behavior documentation.

8. Testing vs Conventions
Testing owns strategy and infrastructure.
Detailed recurring test-writing style belongs to Conventions.

9. Testing vs Operations
CI may be discussed in terms of test execution.
The broader delivery pipeline belongs to Operations.

10. Practical usefulness
Flag purely descriptive inventories that do not help someone actually validate a change.

Acceptance question:

"Could a future engineer determine which tests to add or run, how to execute them, and how this repository normally establishes confidence in a change?"