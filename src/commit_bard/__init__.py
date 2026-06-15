"""Git Commit Bard — your staged diff, returned as verse.

A joy layer on top of a solved problem (AI commit messages). The pipeline
itself — diff -> model -> message, multi-provider, git hook — is well-trodden
(see aicommits, opencommit, aicommit2). What's ours is treating the commit as a
small creative artifact and wrapping it in delight.
"""

__version__ = "0.1.0"

__all__ = ["__version__"]
