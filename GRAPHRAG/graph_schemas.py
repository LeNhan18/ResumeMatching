from pydantic import BaseModel, Field
from typing import List, Optional, Literal

# ---------------------------------
# Schemas attributes for Relationships
# ---------------------------------

class WorkedAtProperties(BaseModel):
    position: Optional[str] = Field(None, description="Job title or position held")
    duration_months: Optional[int] = Field(None, description="Duration of the position in months")
    experience_type: Optional[str] = Field(
        None, description="Type of experience, e.g., Corporate, Internship, Freelance, Personal Project, Academic Project"
    )
    seniority_level: Optional[str] = Field(None, description="Seniority level: Junior, Mid, Senior, Lead, Manager, etc.")

class StudiedAtProperties(BaseModel):
    degree: Optional[str] = Field(None, description="Degree type, examples: Bachelor, Master, PhD, Associate")
    major: Optional[str] = Field(None, description="Field of study or major")
    gpa: Optional[float] = Field(None, description="Grade Point Average (GPA)")
    grad_year: Optional[int] = Field(None, description="Year of graduation")

class EarnedProperties(BaseModel):
    score: Optional[float] = Field(None, description="Point or score achieved in the certificate (if applicable, e.g., 7.5 for IELTS, 250 for TOEIC, 5.0 for HSK)")

class RequiresSkillProperties(BaseModel):
    is_mandatory: bool = Field(description="Whether the skill is mandatory for the job description")

class BuiltProperties(BaseModel):
    project_type: Literal["Personal", "Academic", "Personal Project", "Academic Project", "Project"] = Field(
        description="Type of project: Personal or Academic"
    )
    is_team_project: Optional[bool] = Field(None, description="Whether the project is a team project")
    duration_months: Optional[int] = Field(None, description="Duration of the project in months")

class ParticipatedInProperties(BaseModel):
    rank: Optional[str] = Field(None, description="Rank or achievement in the competition, e.g., Winner, Runner-up, Top 10")

class AlternativeToProperties(BaseModel):
    similarity: float = Field(description="Similarity score between two skills, from 0.0 to 1.0")

# ---------------------------------
# Schemas attributes for Nodes
# ---------------------------------

class ExtractedNode(BaseModel):
    id_node: str = Field(description="Unique identifier for the node (e.g. 'cand_tien', 'job_senior_backend', or a generated uuid/slug)")
    labels: List[Literal[
        "Candidate", "JobPosition", "Company", "Industry", "Skill", 
        "SkillGroup", "School", "Major", "Project", "Certificate", "Competition"
    ]] = Field(description="Labels of the node, representing its types in the graph database")
    name: str = Field(description="Name or title of the node. MUST be translated to English for standardization, EXCEPT for Proper Nouns (Candidate, Company, School names) which should be kept in their original language.")

    # Candidate specific properties
    phone: Optional[str] = Field(None, description="Candidate contact phone number")
    email: Optional[str] = Field(None, description="Candidate email address")
    summary: Optional[str] = Field(None, description="Candidate professional summary or career objective")
    soft_skill: Optional[str] = Field(None, description="Candidate soft skills (comma-separated or text summary)")
    volunteering: Optional[str] = Field(None, description="Candidate volunteering, extra-curricular, or community activities")

    # Project specific properties
    description: Optional[str] = Field(None, description="Short description of the project and the problem solved")


class ExtractedEdge(BaseModel):
    source: str = Field(..., description="ID of source node (Source Node ID).")
    target: str = Field(..., description="ID of target node (Target Node ID).")
    edge_type: Literal[
        "WORKED_AT", "POSTED_BY", "BELONGS_TO", "REQUIRES_SKILL", 
        "STUDIED_AT", "EARNED", "VALIDATES_SKILL", "BUILT", 
        "USES_SKILL", "PARTICIPATED_IN", "ALTERNATIVE_TO",
        "EQUIVALENT_TO", "RELATED_MAJOR", "HELD_POSITION", "STUDIED_MAJOR"
    ] = Field(..., description="Type of relationship between two nodes.")
    
    # Strongly-typed relationship properties based on edge_type
    worked_at_props: Optional[WorkedAtProperties] = Field(None, description="Properties configuration if edge_type is 'WORKED_AT'.")
    studied_at_props: Optional[StudiedAtProperties] = Field(None, description="Properties configuration if edge_type is 'STUDIED_AT'.")
    earned_props: Optional[EarnedProperties] = Field(None, description="Properties configuration if edge_type is 'EARNED'.")
    requires_skill_props: Optional[RequiresSkillProperties] = Field(None, description="Properties configuration if edge_type is 'REQUIRES_SKILL'.")
    built_props: Optional[BuiltProperties] = Field(None, description="Properties configuration if edge_type is 'BUILT'.")
    participated_in_props: Optional[ParticipatedInProperties] = Field(None, description="Properties configuration if edge_type is 'PARTICIPATED_IN'.")
    alternative_to_props: Optional[AlternativeToProperties] = Field(None, description="Properties configuration if edge_type is 'ALTERNATIVE_TO'.")


class GraphExtractionSchema(BaseModel):
    """
    Schema tổng cao nhất (Top-level) để gửi cho LLM Extractor trích xuất toàn bộ dữ liệu tài liệu thành đồ thị.
    """
    nodes: List[ExtractedNode] = Field(..., description="List of all entities detected in the document.")
    edges: List[ExtractedEdge] = Field(..., description="List of all relationships connecting the entities.")


