"""
Pydantic models defining CodeMap's API contracts.

Kept separate from internal representations (networkx graph, dataclasses in
graph/builder.py) on purpose: internal shapes are free to change without
breaking the API, and these models double as auto-generated OpenAPI docs.
"""

from __future__ import annotations

from pydantic import BaseModel, Field, model_validator


class AnalyzeRequest(BaseModel):
    path: str | None = Field(None, description="Absolute path to a local JS/TS repository")
    githubUrl: str | None = Field(None, description="GitHub repository URL, e.g. https://github.com/owner/repo")
    forceRefresh: bool = Field(
        False,
        description="For GitHub sources only: bypass the cache and re-download even if a recent analysis exists.",
    )

    @model_validator(mode="after")
    def exactly_one_source(self):
        if not self.path and not self.githubUrl:
            raise ValueError("Provide either 'path' or 'githubUrl'")
        if self.path and self.githubUrl:
            raise ValueError("Provide only one of 'path' or 'githubUrl', not both")
        return self


class AnalyzeResponse(BaseModel):
    projectId: str
    rootPath: str
    sourceType: str  # "local" | "github"
    sourceLabel: str  # local abs path, or "owner/repo@ref" for GitHub
    fileCount: int
    edgeCount: int
    cycleCount: int  # number of cycles LISTED (capped; see cyclesTruncated)
    cyclesTruncated: bool = False
    cyclicComponentCount: int = 0  # groups of mutually-dependent files
    externalDependencyCount: int
    unresolvedImportCount: int
    cached: bool = False  # true if this result was served from the GitHub cache, no re-fetch/re-parse
    isPrivate: bool = False


class ProjectSummary(BaseModel):
    projectId: str
    rootPath: str
    sourceType: str
    sourceLabel: str
    fileCount: int
    edgeCount: int
    cycleCount: int  # number of cycles LISTED (capped; see cyclesTruncated)
    cyclesTruncated: bool = False
    cyclicComponentCount: int = 0  # groups of mutually-dependent files
    highRiskCount: int
    avgDependencies: float
    createdAt: str
    isPrivate: bool = False


class NodeOut(BaseModel):
    id: str
    filePath: str
    name: str
    language: str = "javascript"
    linesOfCode: int
    inDegree: int
    outDegree: int
    dependencyDepth: int
    degreeCentrality: float
    betweennessCentrality: float | None = None
    inCycle: bool = False
    architectureType: str = "Unknown"
    riskScore: int | None = None
    riskLevel: str | None = None
    riskReasons: list[str] = []


class EdgeOut(BaseModel):
    source: str
    target: str
    type: str
    symbols: list[str] = []


class GraphResponse(BaseModel):
    nodes: list[NodeOut]
    edges: list[EdgeOut]


class FileListItem(BaseModel):
    id: str
    name: str
    filePath: str


class CycleOut(BaseModel):
    id: str
    chain: list[str]


class MetricsResponse(BaseModel):
    fileCount: int
    edgeCount: int
    connectedComponentCount: int
    largestComponentSize: int
    avgDependencies: float
    betweennessSkipped: bool
    externalDependencies: dict[str, int]
    unresolvedImportCount: int


class ImpactResponse(BaseModel):
    fileId: str
    directDependents: list[str]
    indirectDependents: list[str]
    estimatedAffected: int
