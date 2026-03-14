

<skills_system priority="1">

## Available Skills

<!-- SKILLS_TABLE_START -->
<usage>
When users ask you to perform tasks, check if any of the available skills below can help complete the task more effectively. Skills provide specialized capabilities and domain knowledge.

How to use skills:
- Invoke: `npx openskills read <skill-name>` (run in your shell)
  - For multiple: `npx openskills read skill-one,skill-two`
- The skill content will load with detailed instructions on how to complete the task
- Base directory provided in output for resolving bundled resources (references/, scripts/, assets/)

Usage notes:
- Only use skills listed in <available_skills> below
- Do not invoke a skill that is already loaded in your context
- Each skill invocation is stateless
</usage>

<available_skills>

<skill>
<name>auto-coder</name>
<description>Autonomous spec-driven development agent. Syncs DEV_SPEC.md into chapter-based reference files, identifies the next pending task from the schedule, implements code following spec architecture and patterns, runs tests with up to 3 auto-fix rounds, and persists progress with atomic commits. Use when user says "auto code", "自动开发", "自动写代码", "auto dev", "一键开发", "autopilot", or wants fully automated spec-to-code workflow.</description>
<location>project</location>
</skill>

<skill>
<name>qa-tester</name>
<description>"Fully autonomous QA testing agent for Modular RAG MCP Server. Reads test cases from QA_TEST_PLAN.md, executes ALL test types automatically without human intervention — CLI commands, Dashboard UI via Streamlit AppTest headless rendering, MCP protocol via subprocess JSON-RPC, provider switches, and data lifecycle checks. Diagnoses failures, applies fixes with up to 3 retry rounds, and records results in QA_TEST_PROGRESS.md. Use when user says 'run QA', 'QA test', 'QA 测试', '执行测试', '跑测试', 'test and fix', or wants to execute QA test plan."</description>
<location>project</location>
</skill>


<skill>
<name>frontend-design</name>
<description>Create distinctive, production-grade frontend interfaces with high design quality. Use this skill when the user asks to build web components, pages, or applications. Generates creative, polished code that avoids generic AI aesthetics.</description>
<location>project</location>
</skill>

<skill>
<name>python-patterns</name>
<description>Pythonic idioms, PEP 8 standards, type hints, and best practices for building robust, efficient, and maintainable Python applications. Use when writing Python code, designing packages, or reviewing Python implementations.</description>
<location>project</location>
</skill>

<skill>
<name>python-testing</name>
<description>Python testing strategies using pytest, TDD methodology, fixtures, mocking, parametrization, and coverage requirements. Use when writing tests, setting up testing infrastructure, or reviewing test coverage.</description>
<location>project</location>
</skill>

<skill>
<name>api-design</name>
<description>REST API design patterns including resource naming, status codes, pagination, filtering, error responses, versioning, and rate limiting for production APIs. Use when designing or reviewing API endpoints.</description>
<location>project</location>
</skill>

<skill>
<name>backend-patterns</name>
<description>Backend architecture patterns, API design, database optimization, and server-side best practices. Covers Repository/Service patterns, caching, middleware, error handling, and concurrency.</description>
<location>project</location>
</skill>

<skill>
<name>security-review</name>
<description>Comprehensive security checklist and patterns for authentication, input validation, secrets management, SQL injection prevention, XSS/CSRF protection, and rate limiting. Use when implementing auth, handling user input, or working with sensitive data.</description>
<location>project</location>
</skill>

<skill>
<name>frontend-patterns</name>
<description>Frontend development patterns for React/Vue, state management, performance optimization, and UI best practices. Covers component composition, custom hooks, memoization, and accessibility.</description>
<location>project</location>
</skill>


<skill>
<name>iterative-retrieval</name>
<description>Pattern for progressively refining context retrieval in multi-agent workflows. Solves the subagent context problem through dispatch-evaluate-refine loops. Relevant for RAG architectures and hybrid search implementations.</description>
<location>project</location>
</skill>

<skill>
<name>search-first</name>
<description>Research-before-coding workflow. Search for existing tools, libraries, and patterns before writing custom code. Use when starting new features or adding dependencies to avoid reinventing the wheel.</description>
<location>project</location>
</skill>

</available_skills>
<!-- SKILLS_TABLE_END -->

</skills_system>
