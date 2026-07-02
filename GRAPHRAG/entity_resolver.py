import difflib
from GRAPHRAG.graph_schemas import ExtractedNode
from utils.logger import setup_logger

logger = setup_logger("EntityResolver", log_file="entity_resolver.log")

# ==========================================
# LAYER 2: RULE-BASED DICTIONARIES
# ==========================================

SKILL_ALIASES = {
    "fast-api": "FastAPI",
    "fast api": "FastAPI",
    "reactjs": "React JS",
    "react.js": "React JS",
    "react": "React JS",
    "nodejs": "Node.js",
    "node.js": "Node.js",
    "node js": "Node.js",
    "vuejs": "Vue.js",
    "vue.js": "Vue.js",
    "golang": "Go",
    "k8s": "Kubernetes",
    "aws": "Amazon Web Services",
    "gcp": "Google Cloud Platform",
}

SCHOOL_ALIASES = {
    "hust": "Hanoi University of Science and Technology",
    "đại học bách khoa hà nội": "Hanoi University of Science and Technology",
    "bk tphcm": "Ho Chi Minh City University of Technology",
    "đại học bách khoa tphcm": "Ho Chi Minh City University of Technology",
    "uit": "University of Information Technology",
    "đại học công nghệ thông tin": "University of Information Technology",
}

COMPANY_ALIASES = {
    "fpt": "FPT Software",
    "fsoft": "FPT Software",
    "vng": "VNG Corporation",
}

CERT_ALIASES = {
    "aws dev": "AWS Certified Developer",
    "aws certified developer associate": "AWS Certified Developer",
}

INDUSTRY_ALIASES = {
    "fintech": "Financial Technology",
    "ecommerce": "E-Commerce",
    "e-commerce": "E-Commerce",
    "edtech": "Education Technology",
    "healthtech": "Health Technology",
    "logistics": "Logistics & Supply Chain",
    "gaming": "Game Development",
}

SKILLGROUP_ALIASES = {
    "web framework": "Web Frameworks",
    "web frameworks": "Web Frameworks",
    "cloud": "Cloud Computing",
    "cloud computing": "Cloud Computing",
    "db": "Databases",
    "database": "Databases",
    "devops": "DevOps & CI/CD",
    "cicd": "DevOps & CI/CD",
    "ml": "Machine Learning & AI",
    "ai": "Machine Learning & AI",
    "machine learning": "Machine Learning & AI",
}

# ==========================================
# LAYER 3: GOLDEN RECORDS FOR FUZZY MATCHING
# ==========================================

GOLDEN_SKILLS = [
    "FastAPI", "React JS", "Node.js", "Vue.js", "Python", "Java", "C++", 
    "Amazon Web Services", "Google Cloud Platform", "Kubernetes", "Docker",
    "PostgreSQL", "MongoDB", "Redis", "Elasticsearch", "TypeScript", "JavaScript",
    "Machine Learning", "Data Engineering"
]

GOLDEN_SCHOOLS = [
    "Hanoi University of Science and Technology",
    "Ho Chi Minh City University of Technology",
    "University of Information Technology",
    "University of Science",
    "RMIT University"
]

GOLDEN_COMPANIES = [
    "FPT Software",
    "VNG Corporation",
    "Viettel",
    "Shopee",
    "Tiki",
    "MoMo"
]

GOLDEN_CERTS = [
    "AWS Certified Developer",
    "AWS Certified Solutions Architect",
    "Google Cloud Professional",
    "IELTS",
    "TOEIC",
    "TOEFL",
    "HSK",
    "JLPT",
    "PMP",
    "Certified Scrum Master",
]

GOLDEN_INDUSTRIES = [
    "Financial Technology",
    "E-Commerce",
    "Education Technology",
    "Health Technology",
    "Logistics & Supply Chain",
    "Game Development",
    "Enterprise Software",
    "Cybersecurity",
    "Telecommunications",
]

GOLDEN_SKILLGROUPS = [
    "Web Frameworks",
    "Cloud Computing",
    "Databases",
    "DevOps & CI/CD",
    "Machine Learning & AI",
    "Mobile Development",
    "Data Engineering",
    "Security",
    "Networking",
]

class EntityResolver:
    def __init__(self, fuzzy_cutoff: float = 0.8, dynamic_golden_records: dict = None):
        self.fuzzy_cutoff = fuzzy_cutoff
        # Expected format: {"Skill": ["React JS", "FastAPI"], "School": [...]}
        self.dynamic_golden_records = dynamic_golden_records or {}

    def resolve_node(self, node: ExtractedNode, document_id: str = None) -> tuple[str, str]:
        """
        Resolves a single node's name and generates a deterministic ID.
        If the node is a Candidate and document_id is provided, it uses the document_id as the ID.
        Returns: (resolved_name, new_id)
        """
        if not node.name:
            return "", node.id_node

        raw_name = node.name.strip()
        lower_name = raw_name.lower()
        
        resolved_name = raw_name
        labels = node.labels if node.labels else []

        if "Skill" in labels:
            golden = self.dynamic_golden_records.get("Skill", GOLDEN_SKILLS)
            resolved_name = self._resolve(lower_name, raw_name, SKILL_ALIASES, golden)
        elif "School" in labels:
            golden = self.dynamic_golden_records.get("School", GOLDEN_SCHOOLS)
            resolved_name = self._resolve(lower_name, raw_name, SCHOOL_ALIASES, golden)
        elif "Company" in labels:
            golden = self.dynamic_golden_records.get("Company", GOLDEN_COMPANIES)
            resolved_name = self._resolve(lower_name, raw_name, COMPANY_ALIASES, golden)
        elif "Certificate" in labels:
            golden = self.dynamic_golden_records.get("Certificate", GOLDEN_CERTS)
            resolved_name = self._resolve(lower_name, raw_name, CERT_ALIASES, golden)
        elif "Industry" in labels:
            golden = self.dynamic_golden_records.get("Industry", GOLDEN_INDUSTRIES)
            resolved_name = self._resolve(lower_name, raw_name, INDUSTRY_ALIASES, golden)
        elif "SkillGroup" in labels:
            golden = self.dynamic_golden_records.get("SkillGroup", GOLDEN_SKILLGROUPS)
            resolved_name = self._resolve(lower_name, raw_name, SKILLGROUP_ALIASES, golden)
        
        # Determine the prefix for the new ID based on the primary label
        prefix = "node"
        if "Candidate" in labels: prefix = "cand"
        elif "Job" in labels: prefix = "job"
        elif "Company" in labels: prefix = "comp"
        elif "School" in labels: prefix = "school"
        elif "Skill" in labels: prefix = "skill"
        elif "SkillGroup" in labels: prefix = "group"
        elif "Project" in labels: prefix = "proj"
        elif "Certificate" in labels: prefix = "cert"
        elif "Competition" in labels: prefix = "contest"
        elif "Industry" in labels: prefix = "ind"

        # Generate ID
        if "Candidate" in labels and document_id:
            # Force the Candidate Node ID in GraphDB to match the VectorDB ID (UUID)
            new_id = str(document_id)
        else:
            # Generate deterministic ID based on slugified name
            slug = resolved_name.lower().replace(" ", "_").replace(".", "").replace("-", "_").replace("/", "_")
            
            # Clean up multiple underscores
            import re
            slug = re.sub(r'_+', '_', slug)
            
            new_id = f"{prefix}_{slug}"

        if resolved_name != raw_name:
            logger.info(f"Resolved Entity [{labels[0]}]: '{raw_name}' ➔ '{resolved_name}'")

        return resolved_name, new_id

    def _resolve(self, lower_name: str, raw_name: str, aliases: dict, golden_records: list) -> str:
        # Layer 2: Dictionary Lookup
        if lower_name in aliases:
            return aliases[lower_name]
        
        # Layer 3: Fuzzy Matching Use case-insensitive fuzzy matching against Golden Records
        lower_golden = [g.lower() for g in golden_records]
        matches = difflib.get_close_matches(lower_name, lower_golden, n=1, cutoff=self.fuzzy_cutoff)
        
        if matches:
            idx = lower_golden.index(matches[0])
            return golden_records[idx]
            
        return raw_name
