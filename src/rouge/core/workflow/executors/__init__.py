"""Executor classes that run workflow steps driven by declarative configs.

Executors adapt Pydantic configuration models (see
:mod:`rouge.core.workflow.config`) to the :class:`WorkflowStep` runtime
interface.  Each executor is responsible for a single ``kind`` discriminator:
:class:`PromptJsonStep` handles ``"prompt-json"`` configs.
"""
