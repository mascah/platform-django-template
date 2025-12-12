FAQ: How Much Rust?
===================

**Q: How much of this project template uses Rust?**

It is littered with Rust.

The generated template is supported by a considerable amount of Rust tooling. This was not the plan. It simply happened.

+------------------+---------------------------------------------+----------+
| Tool             | Purpose                                     | Language |
+==================+=============================================+==========+
| Turborepo        | Monorepo build orchestration                | Rust     |
+------------------+---------------------------------------------+----------+
| Vite + Rolldown  | Frontend bundling                           | Rust     |
+------------------+---------------------------------------------+----------+
| Ruff             | Python linting and formatting               | Rust     |
+------------------+---------------------------------------------+----------+
| uv               | Python package management                   | Rust     |
+------------------+---------------------------------------------+----------+
| just             | Task runner (justfile)                      | Rust     |
+------------------+---------------------------------------------+----------+
| Lefthook         | Git hooks manager                           | Go       |
+------------------+---------------------------------------------+----------+

**Q: Is Lefthook written in Rust?**

No. Lefthook is written in Go. It remains on this list as a reminder that not everything has been rewritten in Rust yet.

**Q: Should I learn Rust to use this template?**

No. You will never need to write or read Rust code. You will simply install tools and watch them run faster than you expected.

**Q: Why is everything being rewritten in Rust?**

Memory safety.

**Q: Is that the real reason?**

Sometimes it is also performance.
