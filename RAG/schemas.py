from pydantic import BaseModel, Field, model_validator
from typing import List, Dict, Optional

class WorkExperience(BaseModel):
    company: str = Field(description="Name of the company or organization")
    position: str = Field(description="Job title or position held")
    start_date: str = Field(description="Start date (e.g., '2020-03', '03/2020', or '2020')")
    end_date: Optional[str] = Field(None, description="End date (e.g., '2022-05', 'Present', or null if currently working)")
    skills_used: List[str] = Field(default_factory=list, description="Key skills and technologies used in this job")
    seniority_level: str = Field("Mid", description="Seniority level: Junior, Mid, Senior, Lead, Manager, etc.")
    description: Optional[str] = Field(None, description="Brief description of responsibilities and achievements")

class EducationInfo(BaseModel):
    school: str = Field(description="Name of the school, university, or academy")
    degree: Optional[str] = Field(None, description="Degree type (e.g., Bachelor, Master, PhD, Associate)")
    major: Optional[str] = Field(None, description="Field of study or major")
    grad_year: Optional[str] = Field(None, description="Year of graduation (e.g., '2019')")

class CVSchema(BaseModel):
    name: str = Field(description="Full name of the candidate")
    email: Optional[str] = Field(None, description="Candidate's email address")
    phone: Optional[str] = Field(None, description="Candidate's contact phone number")
    skills: List[str] = Field(default_factory=list, description="General skills listed in the CV")
    experience: List[WorkExperience] = Field(default_factory=list, description="Chronological work history")
    education: List[EducationInfo] = Field(default_factory=list, description="Academic background")
    certs: List[str] = Field(default_factory=list, description="Certifications and licenses")
    languages: List[str] = Field(default_factory=list, description="Languages spoken")
    summary: Optional[str] = Field(None, description="Professional summary or bio")
    industry: Optional[str] = Field(None, description="Primary industry (e.g., IT, Banking, Healthcare)")
    domain_specific_fields: Dict[str, str] = Field(default_factory=dict, description="Flexible domain-specific fields")

class JDSchema(BaseModel):
    position: str = Field(description="Target job title")
    required_skills: List[str] = Field(default_factory=list, description="Essential skills and technologies required")
    nice_to_have: List[str] = Field(default_factory=list, description="Preferred or optional skills")
    min_exp_years: float = Field(0.0, description="Minimum years of relevant experience required")
    level: str = Field("Mid", description="Required seniority level (e.g., Junior, Mid, Senior)")
    domain: str = Field(description="Business domain or technical focus area (e.g., Fintech, Backend, DevOps, Sales)")
    industry: str = Field(description="Industry category (e.g., IT, Retail, Healthcare)")
    education_requirement: Optional[str] = Field(None, description="Minimum or preferred education level")
    location: Optional[str] = Field(None, description="Job location")

class ScoringWeights(BaseModel):
    skills: float = Field(default=0.4, ge=0.2, le=0.6, description="Weight for technical skills alignment")
    experience: float = Field(default=0.3, ge=0.1, le=0.5, description="Weight for work experience & domain tenure")
    education: float = Field(default=0.15, ge=0.0, le=0.3, description="Weight for education credentials")
    culture_fit: float = Field(default=0.15, ge=0.0, le=0.3, description="Weight for general soft skills / culture alignment")

    @model_validator(mode="after")
    def check_sum(self):
        total = self.skills + self.experience + self.education + self.culture_fit
        if not (0.95 <= total <= 1.05):
            raise ValueError(f"Total weights sum must be approximately 100% (currently {total})")
        return self

class ScoringBreakdown(BaseModel):
    skills: float = Field(description="Score for skills alignment (0-100)")
    experience: float = Field(description="Score for experience & career path (0-100)")
    education: float = Field(description="Score for education credentials (0-100)")
    culture_fit: float = Field(description="Score for soft skills & overall fit (0-100)")

class ScoringResult(BaseModel):
    match_score: float = Field(description="Final weighted match score (0-100)")
    breakdown: ScoringBreakdown = Field(description="Breakdown of individual score components")
    missing_skills: List[str] = Field(default_factory=list, description="Key skills required in JD but missing or weak in CV")
    strengths: List[str] = Field(default_factory=list, description="Key positive highlights of the candidate")
    reasoning: str = Field(description="Detailed textual feedback justifying the scores")
