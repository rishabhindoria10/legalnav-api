"""
LegalNav Live API - Enhanced Version
=====================================
Real-time legal data integration for IBM watsonx Orchestrate
IBM Dev Day: AI Demystified Hackathon 2026

This API provides:
1. Case Law Search via CourtListener (Free Law Project)
2. Attorney Bar Status Verification URLs
3. NEW: Attorney extraction from winning cases

Deploy to: Railway (recommended), Render, or any container platform
"""

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum
import httpx
import os
import logging
import re
import asyncio

# ============================================================================
# LOGGING CONFIGURATION
# ============================================================================

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("legalnav-api")

# ============================================================================
# FASTAPI APP SETUP
# ============================================================================

app = FastAPI(
    title="LegalNav Live API",
    description="""
## Real-time Legal Data API for IBM watsonx Orchestrate

This API powers the LegalNav multi-agent system, providing:

### 🔍 Case Law Search
Search millions of court opinions via CourtListener (Free Law Project).
Find relevant precedents for tenant rights, employment disputes, family law, and more.

### ✅ Attorney Verification
Get direct links to official state bar verification pages.
Verify attorney credentials before making recommendations.

### 👨‍⚖️ Winning Attorney Extraction (NEW)
Automatically extract attorney information from cases where tenants/plaintiffs won.
Get recommendations for lawyers who have successfully handled similar cases.

### 🏛️ Built for IBM Dev Day: AI Demystified Hackathon 2026

**Data Sources:**
- CourtListener API (Free Law Project) - 8+ million court opinions
- State Bar Association websites - All 50 states + DC

**Note:** This API provides legal information, not legal advice.
    """,
    version="1.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
    contact={
        "name": "LegalNav Team",
        "url": "https://github.com/your-team/legalnav"
    },
    license_info={
        "name": "MIT License"
    }
)

# CORS Middleware - Allow all origins for hackathon demo
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============================================================================
# CONFIGURATION
# ============================================================================

# CourtListener API Token (optional but recommended for higher rate limits)
COURTLISTENER_API_TOKEN = os.getenv("COURTLISTENER_API_TOKEN", "")

# Request timeout in seconds
REQUEST_TIMEOUT = 30.0

# ============================================================================
# ENUMS
# ============================================================================

class USState(str, Enum):
    """US State codes for attorney verification"""
    AL = "AL"
    AK = "AK"
    AZ = "AZ"
    AR = "AR"
    CA = "CA"
    CO = "CO"
    CT = "CT"
    DE = "DE"
    DC = "DC"
    FL = "FL"
    GA = "GA"
    HI = "HI"
    ID = "ID"
    IL = "IL"
    IN = "IN"
    IA = "IA"
    KS = "KS"
    KY = "KY"
    LA = "LA"
    ME = "ME"
    MD = "MD"
    MA = "MA"
    MI = "MI"
    MN = "MN"
    MS = "MS"
    MO = "MO"
    MT = "MT"
    NE = "NE"
    NV = "NV"
    NH = "NH"
    NJ = "NJ"
    NM = "NM"
    NY = "NY"
    NC = "NC"
    ND = "ND"
    OH = "OH"
    OK = "OK"
    OR = "OR"
    PA = "PA"
    RI = "RI"
    SC = "SC"
    SD = "SD"
    TN = "TN"
    TX = "TX"
    UT = "UT"
    VT = "VT"
    VA = "VA"
    WA = "WA"
    WV = "WV"
    WI = "WI"
    WY = "WY"

# ============================================================================
# PYDANTIC MODELS - REQUEST
# ============================================================================

class CaseSearchRequest(BaseModel):
    """Request model for case law search"""
    query: str = Field(
        ...,
        min_length=3,
        max_length=500,
        description="Search terms describing the legal issue. Use specific legal concepts.",
        examples=["tenant eviction habitability warranty", "wrongful termination whistleblower"]
    )
    jurisdiction: Optional[str] = Field(
        None,
        min_length=2,
        max_length=10,
        description="Court jurisdiction code (e.g., 'ca' for California, 'scotus' for Supreme Court)",
        examples=["ca", "ny", "tex", "scotus"]
    )
    date_after: Optional[str] = Field(
        None,
        pattern=r"^\d{4}-\d{2}-\d{2}$",
        description="Only return cases filed after this date (YYYY-MM-DD format)",
        examples=["2020-01-01", "2023-06-15"]
    )
    limit: int = Field(
        default=5,
        ge=1,
        le=20,
        description="Maximum number of results to return (1-20)"
    )

class CaseSearchWithAttorneysRequest(BaseModel):
    """Request model for case law search with attorney extraction"""
    query: str = Field(
        ...,
        min_length=3,
        max_length=500,
        description="Search terms describing the legal issue.",
        examples=["tenant eviction retaliatory habitability"]
    )
    jurisdiction: Optional[str] = Field(
        None,
        description="Court jurisdiction code (e.g., 'ca' for California)",
        examples=["ca", "ny", "tx"]
    )
    date_after: Optional[str] = Field(
        None,
        pattern=r"^\d{4}-\d{2}-\d{2}$",
        description="Only return cases filed after this date (YYYY-MM-DD)",
        examples=["2023-01-01"]
    )
    party_type: str = Field(
        default="appellant",
        description="Which party's attorneys to extract: 'appellant', 'appellee', 'plaintiff', 'defendant', 'tenant', 'all'",
        examples=["tenant", "appellant", "plaintiff"]
    )
    limit: int = Field(
        default=5,
        ge=1,
        le=10,
        description="Maximum number of cases to search (1-10, lower = faster)"
    )

class VerifyAttorneyRequest(BaseModel):
    """Request model for attorney bar verification"""
    state: str = Field(
        ...,
        min_length=2,
        max_length=2,
        description="Two-letter US state code (uppercase)",
        examples=["CA", "TX", "NY", "FL"]
    )
    bar_number: str = Field(
        ...,
        min_length=1,
        max_length=20,
        description="Attorney's bar number as issued by the state bar",
        examples=["123456", "TX12345678"]
    )

class AttorneyLookupRequest(BaseModel):
    """Request model for looking up attorneys from a specific case"""
    case_url: str = Field(
        ...,
        description="CourtListener opinion URL",
        examples=["https://www.courtlistener.com/opinion/10617915/ceron-v-liu/"]
    )
    party_type: Optional[str] = Field(
        default="all",
        description="Which party's attorneys to extract: 'appellant', 'appellee', 'plaintiff', 'defendant', 'all'"
    )

# ============================================================================
# PYDANTIC MODELS - RESPONSE
# ============================================================================

class AttorneyInfo(BaseModel):
    """Information about an attorney"""
    name: str = Field(..., description="Attorney's name")
    role: Optional[str] = Field(None, description="Role in the case (e.g., 'For Appellant')")
    firm: Optional[str] = Field(None, description="Law firm name if available")
    party_represented: Optional[str] = Field(None, description="Which party they represented")
    source: str = Field(..., description="How this info was obtained: 'docket', 'opinion_text', 'search_result'")

class CaseResult(BaseModel):
    """Individual case result from search"""
    case_name: str = Field(..., description="Full case name (e.g., 'Smith v. Jones')")
    citation: Optional[str] = Field(None, description="Official legal citation if available")
    date_filed: str = Field(..., description="Date the case was filed or decided")
    court: str = Field(..., description="Name of the court")
    court_id: Optional[str] = Field(None, description="CourtListener court identifier")
    summary: Optional[str] = Field(None, description="Brief excerpt from the opinion")
    url: str = Field(..., description="Link to read the full opinion on CourtListener")

class CaseWithAttorneys(BaseModel):
    """Case result with extracted attorney information"""
    case_name: str
    citation: Optional[str] = None
    date_filed: str
    court: str
    url: str
    outcome_summary: Optional[str] = None
    attorneys: List[AttorneyInfo] = Field(default_factory=list)
    docket_id: Optional[int] = None
    cluster_id: Optional[int] = None

class CaseSearchResponse(BaseModel):
    """Response model for case law search"""
    success: bool = Field(True, description="Whether the search was successful")
    cases: List[CaseResult] = Field(default_factory=list, description="List of matching cases")
    total_results: int = Field(0, description="Total matching cases (may exceed limit)")
    query_used: str = Field(..., description="The search query that was executed")
    source: str = Field("CourtListener (Free Law Project)", description="Data source attribution")
    source_url: str = Field("https://www.courtlistener.com", description="Link to data source")
    retrieved_at: str = Field(..., description="ISO timestamp of when search was performed")
    disclaimer: str = Field(
        "This is legal information, not legal advice. Case law interpretation varies by jurisdiction and circumstances.",
        description="Legal disclaimer"
    )

class AttorneySearchResponse(BaseModel):
    """Response model for case search with attorney extraction"""
    success: bool = True
    cases_analyzed: int = Field(..., description="Number of cases analyzed")
    attorneys_found: List[AttorneyInfo] = Field(default_factory=list, description="All attorneys found across cases")
    cases_with_attorneys: List[CaseWithAttorneys] = Field(default_factory=list, description="Cases with their attorneys")
    unique_attorneys: List[Dict[str, Any]] = Field(default_factory=list, description="Deduplicated list of attorneys with case counts")
    query_used: str
    party_filter: str
    source: str = "CourtListener (Free Law Project)"
    retrieved_at: str
    disclaimer: str = "Attorney information is extracted from court records. Verify current bar status before contacting. This is legal information, not legal advice."

class VerifyAttorneyResponse(BaseModel):
    """Response model for attorney verification"""
    success: bool = Field(True, description="Whether the lookup was successful")
    verified: Optional[bool] = Field(None, description="Verification status (null = manual check required)")
    status: str = Field(..., description="Status message")
    name: Optional[str] = Field(None, description="Attorney's name if available")
    admission_date: Optional[str] = Field(None, description="Bar admission date if available")
    discipline_history: bool = Field(False, description="Whether disciplinary records exist")
    verification_url: str = Field(..., description="URL to verify attorney credentials")
    state_bar_name: str = Field(..., description="Name of the state bar association")
    instructions: str = Field(..., description="Instructions for verification")
    retrieved_at: str = Field(..., description="ISO timestamp")

class HealthResponse(BaseModel):
    """Response model for health check"""
    status: str
    service: str
    version: str
    timestamp: str
    courtlistener_configured: bool

class ErrorResponse(BaseModel):
    """Error response model"""
    success: bool = False
    error: str
    error_code: str
    timestamp: str

# ============================================================================
# STATE BAR INFORMATION
# ============================================================================

STATE_BAR_INFO = {
    "AL": {"name": "Alabama State Bar", "url": "https://www.alabar.org/for-the-public/find-a-lawyer/", "instructions": "Search by name or bar number"},
    "AK": {"name": "Alaska Bar Association", "url": "https://www.alaskabar.org/attorney-directory/", "instructions": "Search by name or bar number"},
    "AZ": {"name": "State Bar of Arizona", "url": "https://www.azbar.org/for-the-public/find-a-lawyer/", "instructions": "Search by name or bar number"},
    "AR": {"name": "Arkansas Bar Association", "url": "https://www.arkbar.com/for-the-public/lawyer-search", "instructions": "Search by name"},
    "CA": {"name": "State Bar of California", "url": "https://apps.calbar.ca.gov/attorney/Licensee/Detail/", "instructions": "Add the bar number to the end of the URL, or search at calbar.ca.gov"},
    "CO": {"name": "Colorado Supreme Court Office of Attorney Regulation", "url": "https://www.coloradosupremecourt.com/Search/AttSearch.asp", "instructions": "Search by name or registration number"},
    "CT": {"name": "Connecticut Bar Association", "url": "https://www.jud.ct.gov/attorneyfirminquiry/", "instructions": "Search by name or juris number"},
    "DE": {"name": "Delaware State Bar Association", "url": "https://courts.delaware.gov/forms/download.aspx?id=39492", "instructions": "Search by name"},
    "DC": {"name": "District of Columbia Bar", "url": "https://www.dcbar.org/membership/members", "instructions": "Search by name or bar number"},
    "FL": {"name": "The Florida Bar", "url": "https://www.floridabar.org/directories/find-mbr/", "instructions": "Search by name or bar number"},
    "GA": {"name": "State Bar of Georgia", "url": "https://www.gabar.org/membersearchresults.cfm", "instructions": "Search by name or bar number"},
    "HI": {"name": "Hawaii State Bar Association", "url": "https://hsba.org/HSBA/For_the_Public/Find_a_Lawyer/HSBA/FOR_THE_PUBLIC/Find_a_Lawyer.aspx", "instructions": "Search by name"},
    "ID": {"name": "Idaho State Bar", "url": "https://isb.idaho.gov/licensing/attorney-roster/", "instructions": "Search by name"},
    "IL": {"name": "ARDC Illinois", "url": "https://www.iardc.org/lawyersearch.asp", "instructions": "Search by name or registration number"},
    "IN": {"name": "Indiana Supreme Court Roll of Attorneys", "url": "https://courtapps.in.gov/rollofattorneys/", "instructions": "Search by name or attorney number"},
    "IA": {"name": "Iowa Judicial Branch", "url": "https://www.iacourtcommissions.org/iowaattorney/attorney.do", "instructions": "Search by name or bar number"},
    "KS": {"name": "Kansas Bar Association", "url": "https://www.kscourts.org/attorney", "instructions": "Search by name or bar number"},
    "KY": {"name": "Kentucky Bar Association", "url": "https://www.kybar.org/search/custom.asp?id=2972", "instructions": "Search by name or bar number"},
    "LA": {"name": "Louisiana State Bar Association", "url": "https://www.lsba.org/Public/FindLawyer.aspx", "instructions": "Search by name or bar number"},
    "ME": {"name": "Maine Board of Overseers of the Bar", "url": "https://www.mebaroverseers.org/attorney_search.html", "instructions": "Search by name or bar number"},
    "MD": {"name": "Maryland Courts Attorney Search", "url": "https://mdcourts.gov/attygrievance/attorneysearch", "instructions": "Search by name or ID"},
    "MA": {"name": "Massachusetts Board of Bar Overseers", "url": "https://www.massbbo.org/AttorneySearch", "instructions": "Search by name or BBO number"},
    "MI": {"name": "State Bar of Michigan", "url": "https://www.michbar.org/member/MemberDirectory", "instructions": "Search by name or P number"},
    "MN": {"name": "Minnesota Lawyer Registration", "url": "https://www.mncourts.gov/Find-a-Lawyer.aspx", "instructions": "Search by name or ID"},
    "MS": {"name": "Mississippi Bar", "url": "https://www.msbar.org/for-the-public/attorney-directory/", "instructions": "Search by name or bar number"},
    "MO": {"name": "Missouri Bar", "url": "https://mobar.org/public/AttorneyDirectorySearch.aspx", "instructions": "Search by name or bar number"},
    "MT": {"name": "State Bar of Montana", "url": "https://www.montanabar.org/page/FindLegalHelp", "instructions": "Search by name"},
    "NE": {"name": "Nebraska State Bar Association", "url": "https://www.nebar.com/search/custom.asp?id=2040", "instructions": "Search by name"},
    "NV": {"name": "State Bar of Nevada", "url": "https://nvbar.org/member-services/member-directory/", "instructions": "Search by name or bar number"},
    "NH": {"name": "New Hampshire Bar Association", "url": "https://www.nhbar.org/lawyer-referral-service/", "instructions": "Search by name"},
    "NJ": {"name": "New Jersey Courts Attorney Search", "url": "https://portal.njcourts.gov/webcivilcj/CJWebApp/pages/showAttorneyInfo.faces", "instructions": "Search by name or ID"},
    "NM": {"name": "State Bar of New Mexico", "url": "https://www.sbnm.org/For-Public/Find-A-Lawyer", "instructions": "Search by name"},
    "NY": {"name": "New York Courts Attorney Search", "url": "https://iapps.courts.state.ny.us/attorneyservices/search", "instructions": "Search by name or registration number"},
    "NC": {"name": "North Carolina State Bar", "url": "https://www.ncbar.gov/for-the-public/find-a-lawyer/", "instructions": "Search by name or bar number"},
    "ND": {"name": "State Bar Association of North Dakota", "url": "https://www.sband.org/search/custom.asp?id=5512", "instructions": "Search by name"},
    "OH": {"name": "Ohio Supreme Court Attorney Directory", "url": "https://www.supremecourt.ohio.gov/AttorneySearch/", "instructions": "Search by name or registration number"},
    "OK": {"name": "Oklahoma Bar Association", "url": "https://www.okbar.org/freelegalinfo/findingalawyer/", "instructions": "Search by name or bar number"},
    "OR": {"name": "Oregon State Bar", "url": "https://www.osbar.org/members/membersearch.asp", "instructions": "Search by name or bar number"},
    "PA": {"name": "Pennsylvania Bar Association", "url": "https://www.padisciplinaryboard.org/for-the-public/find-attorney", "instructions": "Search by name or ID"},
    "RI": {"name": "Rhode Island Bar Association", "url": "https://www.ribar.com/for-the-public/find-a-lawyer/", "instructions": "Search by name"},
    "SC": {"name": "South Carolina Bar", "url": "https://www.scbar.org/lawyers/lawyer-directory/", "instructions": "Search by name or bar number"},
    "SD": {"name": "State Bar of South Dakota", "url": "https://www.statebarofsouthdakota.com/find-a-lawyer", "instructions": "Search by name"},
    "TN": {"name": "Tennessee Board of Professional Responsibility", "url": "https://www.tbpr.org/attorneys", "instructions": "Search by name or BPR number"},
    "TX": {"name": "State Bar of Texas", "url": "https://www.texasbar.com/AM/Template.cfm?Section=Find_A_Lawyer", "instructions": "Search by name or bar number"},
    "UT": {"name": "Utah State Bar", "url": "https://www.utahbar.org/public-services/find-a-lawyer/", "instructions": "Search by name or bar number"},
    "VT": {"name": "Vermont Bar Association", "url": "https://www.vtbar.org/find-a-lawyer/", "instructions": "Search by name"},
    "VA": {"name": "Virginia State Bar", "url": "https://www.vsb.org/attorney/attSearch.asp", "instructions": "Search by name or VSB number"},
    "WA": {"name": "Washington State Bar Association", "url": "https://www.mywsba.org/PersonifyEbusiness/LegalDirectory.aspx", "instructions": "Search by name or bar number"},
    "WV": {"name": "West Virginia State Bar", "url": "https://wvbar.org/for-the-public/find-a-lawyer/", "instructions": "Search by name"},
    "WI": {"name": "State Bar of Wisconsin", "url": "https://www.wisbar.org/forPublic/FindaLawyer/Pages/Find-a-Lawyer.aspx", "instructions": "Search by name or bar number"},
    "WY": {"name": "Wyoming State Bar", "url": "https://www.wyomingbar.org/for-the-public/find-a-lawyer/", "instructions": "Search by name"}
}

# ============================================================================
# COURTLISTENER JURISDICTIONS
# ============================================================================

COURTLISTENER_JURISDICTIONS = {
    "ca": ["cal", "calctapp", "calappdeptsuperct"],
    "tx": ["tex", "texapp", "texcrimapp"],
    "ny": ["ny", "nyappdiv", "nyappterm"],
    "fl": ["fla", "fladistctapp"],
    "il": ["ill", "illappct"],
    "pa": ["pa", "pasuperct", "pacommwct"],
    "oh": ["ohio", "ohioctapp"],
    "ga": ["ga", "gactapp"],
    "nc": ["nc", "ncctapp"],
    "nj": ["nj", "njsuperctappdiv"],
    "mi": ["mich", "michctapp"],
    "va": ["va", "vactapp"],
    "wa": ["wash", "washctapp"],
    "az": ["ariz", "arizctapp"],
    "ma": ["mass", "massappct"],
    "in": ["ind", "indctapp"],
    "tn": ["tenn", "tennctapp"],
    "mo": ["mo", "moctapp"],
    "md": ["md", "mdctspecapp"],
    "wi": ["wis", "wisctapp"],
    "co": ["colo", "coloctapp"],
    "mn": ["minn", "minnctapp"],
    "al": ["ala", "alactapp"],
    "sc": ["sc", "scctapp"],
    "la": ["la", "lactapp"],
    "ky": ["ky", "kyctapp"],
    "or": ["or", "orctapp"],
    "ok": ["okla", "oklacivapp", "oklacrimapp"],
    "ct": ["conn", "connappct"],
    "ia": ["iowa", "iowactapp"],
    "ms": ["miss", "missctapp"],
    "ar": ["ark", "arkctapp"],
    "ks": ["kan", "kanctapp"],
    "ut": ["utah", "utahctapp"],
    "nv": ["nev", "nevapp"],
    "nm": ["nm", "nmctapp"],
    "ne": ["neb", "nebctapp"],
    "wv": ["wva"],
    "id": ["idaho", "idahoctapp"],
    "hi": ["haw", "hawapp"],
    "me": ["me"],
    "nh": ["nh"],
    "ri": ["ri"],
    "mt": ["mont"],
    "de": ["del", "delch", "delsuperct"],
    "sd": ["sd"],
    "nd": ["nd", "ndctapp"],
    "ak": ["alaska", "alaskactapp"],
    "dc": ["dc", "dcctapp"],
    "vt": ["vt"],
    "wy": ["wyo"],
    "scotus": ["scotus"],
    "federal": ["ca1", "ca2", "ca3", "ca4", "ca5", "ca6", "ca7", "ca8", "ca9", "ca10", "ca11", "cadc", "cafc"]
}

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def get_timestamp() -> str:
    """Get current UTC timestamp in ISO format"""
    return datetime.utcnow().isoformat() + "Z"

def build_verification_url(state: str, bar_number: str) -> str:
    """Build the verification URL for a state, with direct linking if available"""
    state = state.upper()
    info = STATE_BAR_INFO.get(state, {})
    if state == "CA" and bar_number:
        return f"https://apps.calbar.ca.gov/attorney/Licensee/Detail/{bar_number}"
    return info.get("url", "https://www.americanbar.org/groups/legal_services/flh-home/")

def build_court_filter_query(jurisdiction: str) -> str:
    """Build court filter query string for CourtListener Search API."""
    jurisdiction = jurisdiction.lower()
    if jurisdiction in COURTLISTENER_JURISDICTIONS:
        court_ids = COURTLISTENER_JURISDICTIONS[jurisdiction]
        if len(court_ids) == 1:
            return f"court_id:{court_ids[0]}"
        else:
            court_clauses = [f"court_id:{cid}" for cid in court_ids]
            return "(" + " OR ".join(court_clauses) + ")"
    else:
        return f"court_id:{jurisdiction}"

def extract_attorneys_from_text(text: str, party_filter: str = "all") -> List[AttorneyInfo]:
    """
    Extract attorney names from opinion text using pattern matching.
    
    California appellate opinions typically have attorney info in formats like:
    - "John Smith, for Appellant."
    - "Jane Doe, Attorney at Law, for Respondent."
    - "Law Offices of John Smith for Plaintiff and Appellant"
    - "Smith & Associates, for Defendant"
    """
    attorneys = []
    
    if not text:
        return attorneys
    
    # Common patterns for attorney listings in California appellate opinions
    patterns = [
        # Pattern: "Name, for Party" or "Name for Party"
        r'([A-Z][a-z]+(?:\s+[A-Z]\.?\s*)?(?:\s+[A-Z][a-z]+)+)(?:,?\s+(?:Attorney(?:s)?\s+(?:at\s+Law)?)?)?[,\s]+for\s+(Appellant|Appellee|Respondent|Plaintiff|Defendant|Petitioner|Real Part(?:y|ies) in Interest)',
        
        # Pattern: "Law Offices of Name"
        r'(Law\s+Offices?\s+of\s+[A-Z][a-z]+(?:\s+[A-Z]\.?\s*)?(?:\s+[A-Z][a-z]+)*)[,\s]+for\s+(Appellant|Appellee|Respondent|Plaintiff|Defendant|Petitioner)',
        
        # Pattern: "Name & Associates" or "Name, Smith & Jones"
        r'([A-Z][a-z]+(?:\s+[A-Z]\.?\s*)?(?:\s+[A-Z][a-z]+)*(?:\s*(?:&|and)\s*[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)?(?:\s*,\s*LLP|LLC|PC|P\.C\.)?)[,\s]+for\s+(Appellant|Appellee|Respondent|Plaintiff|Defendant|Petitioner)',
        
        # Pattern: Attorney General offices
        r'((?:Office\s+of\s+)?(?:the\s+)?(?:California\s+)?Attorney\s+General[^,]*),?\s+for\s+(Appellant|Appellee|Respondent|Plaintiff|Defendant)',
        
        # Pattern for "Counsel for X:" sections
        r'(?:Counsel|Attorney(?:s)?)\s+for\s+(Appellant|Appellee|Respondent|Plaintiff|Defendant)[:\s]+([A-Z][a-z]+(?:\s+[A-Z]\.?\s*)?(?:\s+[A-Z][a-z]+)+)',
    ]
    
    # Party type mapping for filtering
    party_aliases = {
        "appellant": ["appellant", "plaintiff", "petitioner"],
        "appellee": ["appellee", "respondent", "defendant"],
        "plaintiff": ["plaintiff", "appellant", "petitioner"],
        "defendant": ["defendant", "appellee", "respondent"],
        "tenant": ["appellant", "plaintiff", "petitioner", "tenant"],  # Tenants are usually appellants in eviction appeals
        "landlord": ["appellee", "respondent", "defendant", "landlord"],
    }
    
    filter_parties = party_aliases.get(party_filter.lower(), []) if party_filter != "all" else []
    
    for pattern in patterns:
        matches = re.finditer(pattern, text, re.IGNORECASE | re.MULTILINE)
        for match in matches:
            groups = match.groups()
            if len(groups) >= 2:
                # Determine which group is the name and which is the party
                if "for" in pattern.lower() and groups[0]:
                    name = groups[0].strip()
                    party = groups[1].strip() if len(groups) > 1 else "Unknown"
                else:
                    party = groups[0].strip()
                    name = groups[1].strip() if len(groups) > 1 else ""
                
                # Skip if name is empty or too short
                if not name or len(name) < 3:
                    continue
                
                # Apply party filter if specified
                if filter_parties:
                    party_lower = party.lower()
                    if not any(fp in party_lower for fp in filter_parties):
                        continue
                
                # Clean up the name
                name = re.sub(r'\s+', ' ', name).strip()
                name = re.sub(r',$', '', name)
                
                # Skip common false positives
                skip_words = ['the court', 'this court', 'trial court', 'superior court', 
                             'we conclude', 'we hold', 'we reverse', 'we affirm']
                if any(sw in name.lower() for sw in skip_words):
                    continue
                
                attorneys.append(AttorneyInfo(
                    name=name,
                    role=f"For {party}",
                    firm=None,
                    party_represented=party,
                    source="opinion_text"
                ))
    
    # Deduplicate by name
    seen_names = set()
    unique_attorneys = []
    for atty in attorneys:
        name_lower = atty.name.lower()
        if name_lower not in seen_names:
            seen_names.add(name_lower)
            unique_attorneys.append(atty)
    
    return unique_attorneys

async def fetch_opinion_text(cluster_id: int, client: httpx.AsyncClient, headers: dict) -> Optional[str]:
    """Fetch the full opinion text for a case from CourtListener."""
    try:
        # First get the opinion IDs from the cluster
        cluster_url = f"https://www.courtlistener.com/api/rest/v4/clusters/{cluster_id}/"
        response = await client.get(cluster_url, headers=headers)
        
        if response.status_code != 200:
            logger.warning(f"Failed to fetch cluster {cluster_id}: {response.status_code}")
            return None
        
        cluster_data = response.json()
        
        # Get the sub_opinions which contain links to opinion objects
        sub_opinions = cluster_data.get("sub_opinions", [])
        
        if not sub_opinions:
            return None
        
        # Fetch the first (main) opinion's text
        # sub_opinions are URLs like "https://www.courtlistener.com/api/rest/v4/opinions/12345/"
        opinion_url = sub_opinions[0] if isinstance(sub_opinions[0], str) else None
        
        if not opinion_url:
            return None
        
        opinion_response = await client.get(opinion_url, headers=headers)
        
        if opinion_response.status_code != 200:
            return None
        
        opinion_data = opinion_response.json()
        
        # Try different text fields
        text = opinion_data.get("html_with_citations") or opinion_data.get("plain_text") or opinion_data.get("html") or ""
        
        # Strip HTML tags for pattern matching
        text = re.sub(r'<[^>]+>', ' ', text)
        text = re.sub(r'\s+', ' ', text)
        
        return text[:50000]  # Limit to first 50k chars to avoid memory issues
        
    except Exception as e:
        logger.error(f"Error fetching opinion text for cluster {cluster_id}: {e}")
        return None

async def fetch_parties_and_attorneys(docket_id: int, client: httpx.AsyncClient, headers: dict) -> List[AttorneyInfo]:
    """
    Fetch parties and attorneys from the docket API.
    Note: This works best for federal PACER cases.
    """
    attorneys = []
    
    try:
        parties_url = f"https://www.courtlistener.com/api/rest/v4/parties/?docket={docket_id}"
        response = await client.get(parties_url, headers=headers)
        
        if response.status_code != 200:
            logger.info(f"No parties data for docket {docket_id}: {response.status_code}")
            return attorneys
        
        data = response.json()
        results = data.get("results", [])
        
        for party in results:
            party_name = party.get("name", "Unknown Party")
            party_type = party.get("party_types", [{}])
            party_type_name = party_type[0].get("name", "Unknown") if party_type else "Unknown"
            
            # Get attorneys for this party
            party_attorneys = party.get("attorneys", [])
            for atty in party_attorneys:
                atty_name = atty.get("name", "")
                if atty_name:
                    attorneys.append(AttorneyInfo(
                        name=atty_name,
                        role=f"For {party_type_name}",
                        firm=atty.get("contact_raw", ""),
                        party_represented=party_name,
                        source="docket"
                    ))
        
    except Exception as e:
        logger.error(f"Error fetching parties for docket {docket_id}: {e}")
    
    return attorneys

# ============================================================================
# COURTLISTENER API INTEGRATION
# ============================================================================

async def search_courtlistener(
    query: str,
    jurisdiction: Optional[str] = None,
    date_after: Optional[str] = None,
    limit: int = 5
) -> CaseSearchResponse:
    """Search CourtListener for case law"""
    
    base_url = "https://www.courtlistener.com/api/rest/v4/search/"
    
    search_query = query
    if jurisdiction:
        court_filter = build_court_filter_query(jurisdiction)
        search_query = f"{query} {court_filter}"
    
    params = {
        "q": search_query,
        "type": "o",
        "order_by": "score desc",
        "page_size": min(limit, 20)
    }
    
    if date_after:
        params["filed_after"] = date_after
    
    headers = {"User-Agent": "LegalNav-API/1.1 (IBM-DevDay-Hackathon)"}
    if COURTLISTENER_API_TOKEN:
        headers["Authorization"] = f"Token {COURTLISTENER_API_TOKEN}"
    
    logger.info(f"Searching CourtListener: query='{search_query}', limit={limit}")
    
    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
        try:
            response = await client.get(base_url, params=params, headers=headers)
            response.raise_for_status()
            data = response.json()
            
            cases = []
            for result in data.get("results", [])[:limit]:
                citations = result.get("citation", [])
                citation = citations[0] if isinstance(citations, list) and citations else (citations if isinstance(citations, str) else None)
                
                snippet = result.get("snippet", "")
                if snippet:
                    snippet = snippet.replace("<mark>", "**").replace("</mark>", "**")
                    snippet = snippet[:500] + "..." if len(snippet) > 500 else snippet
                
                absolute_url = result.get("absolute_url", "")
                if absolute_url and not absolute_url.startswith("http"):
                    absolute_url = f"https://www.courtlistener.com{absolute_url}"
                elif not absolute_url:
                    cluster_id = result.get("cluster_id", "")
                    if cluster_id:
                        absolute_url = f"https://www.courtlistener.com/opinion/{cluster_id}/"
                
                cases.append(CaseResult(
                    case_name=result.get("caseName", result.get("case_name", "Unknown Case")),
                    citation=citation,
                    date_filed=result.get("dateFiled", result.get("date_filed", "Unknown")),
                    court=result.get("court", result.get("court_id", "Unknown Court")),
                    court_id=result.get("court_id"),
                    summary=snippet if snippet else None,
                    url=absolute_url if absolute_url else "https://www.courtlistener.com"
                ))
            
            return CaseSearchResponse(
                success=True,
                cases=cases,
                total_results=data.get("count", 0),
                query_used=search_query,
                retrieved_at=get_timestamp()
            )
            
        except httpx.HTTPStatusError as e:
            logger.error(f"CourtListener HTTP error: {e.response.status_code}")
            raise HTTPException(status_code=e.response.status_code, detail=f"CourtListener API error: {e.response.text}")
        except httpx.TimeoutException:
            raise HTTPException(status_code=504, detail="Search request timed out.")
        except Exception as e:
            logger.error(f"Search failed: {e}")
            raise HTTPException(status_code=500, detail=f"Search failed: {str(e)}")

async def search_with_attorney_extraction(
    query: str,
    jurisdiction: Optional[str] = None,
    date_after: Optional[str] = None,
    party_filter: str = "all",
    limit: int = 5
) -> AttorneySearchResponse:
    """
    Search cases and extract attorney information from each result.
    """
    
    base_url = "https://www.courtlistener.com/api/rest/v4/search/"
    
    search_query = query
    if jurisdiction:
        court_filter = build_court_filter_query(jurisdiction)
        search_query = f"{query} {court_filter}"
    
    params = {
        "q": search_query,
        "type": "o",
        "order_by": "score desc",
        "page_size": min(limit, 10)
    }
    
    if date_after:
        params["filed_after"] = date_after
    
    headers = {"User-Agent": "LegalNav-API/1.1 (IBM-DevDay-Hackathon)"}
    if COURTLISTENER_API_TOKEN:
        headers["Authorization"] = f"Token {COURTLISTENER_API_TOKEN}"
    
    logger.info(f"Searching with attorney extraction: query='{search_query}', party_filter='{party_filter}'")
    
    all_attorneys: List[AttorneyInfo] = []
    cases_with_attorneys: List[CaseWithAttorneys] = []
    
    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
        try:
            response = await client.get(base_url, params=params, headers=headers)
            response.raise_for_status()
            data = response.json()
            
            results = data.get("results", [])[:limit]
            
            # Process each case to extract attorneys
            for result in results:
                cluster_id = result.get("cluster_id")
                docket_id = result.get("docket_id")
                
                citations = result.get("citation", [])
                citation = citations[0] if isinstance(citations, list) and citations else None
                
                absolute_url = result.get("absolute_url", "")
                if absolute_url and not absolute_url.startswith("http"):
                    absolute_url = f"https://www.courtlistener.com{absolute_url}"
                elif not absolute_url and cluster_id:
                    absolute_url = f"https://www.courtlistener.com/opinion/{cluster_id}/"
                
                case_attorneys = []
                
                # Method 1: Check if attorney field is populated in search results
                search_attorney = result.get("attorney", "")
                if search_attorney:
                    case_attorneys.append(AttorneyInfo(
                        name=search_attorney,
                        role="From case record",
                        firm=None,
                        party_represented=None,
                        source="search_result"
                    ))
                
                # Method 2: Try to get attorneys from docket/parties API (works for federal cases)
                if docket_id:
                    docket_attorneys = await fetch_parties_and_attorneys(docket_id, client, headers)
                    case_attorneys.extend(docket_attorneys)
                
                # Method 3: Extract from opinion text (works for state appellate cases)
                if cluster_id and len(case_attorneys) < 2:  # Only fetch text if we don't have much data
                    opinion_text = await fetch_opinion_text(cluster_id, client, headers)
                    if opinion_text:
                        text_attorneys = extract_attorneys_from_text(opinion_text, party_filter)
                        case_attorneys.extend(text_attorneys)
                
                # Filter attorneys by party type if specified
                if party_filter != "all" and case_attorneys:
                    party_aliases = {
                        "appellant": ["appellant", "plaintiff", "petitioner"],
                        "appellee": ["appellee", "respondent", "defendant"],
                        "tenant": ["appellant", "plaintiff", "petitioner", "tenant"],
                        "landlord": ["appellee", "respondent", "defendant", "landlord"],
                    }
                    filter_terms = party_aliases.get(party_filter.lower(), [party_filter.lower()])
                    case_attorneys = [
                        a for a in case_attorneys 
                        if a.party_represented and any(ft in a.party_represented.lower() for ft in filter_terms)
                        or a.role and any(ft in a.role.lower() for ft in filter_terms)
                        or a.source == "search_result"  # Keep search results even if party unknown
                    ]
                
                snippet = result.get("snippet", "")
                if snippet:
                    snippet = re.sub(r'<[^>]+>', '', snippet)[:300]
                
                cases_with_attorneys.append(CaseWithAttorneys(
                    case_name=result.get("caseName", "Unknown Case"),
                    citation=citation,
                    date_filed=result.get("dateFiled", "Unknown"),
                    court=result.get("court", "Unknown Court"),
                    url=absolute_url,
                    outcome_summary=snippet,
                    attorneys=case_attorneys,
                    docket_id=docket_id,
                    cluster_id=cluster_id
                ))
                
                all_attorneys.extend(case_attorneys)
            
            # Create deduplicated list with case counts
            attorney_counts: Dict[str, Dict[str, Any]] = {}
            for atty in all_attorneys:
                name_key = atty.name.lower().strip()
                if name_key not in attorney_counts:
                    attorney_counts[name_key] = {
                        "name": atty.name,
                        "roles": set(),
                        "firms": set(),
                        "case_count": 0,
                        "sources": set()
                    }
                attorney_counts[name_key]["case_count"] += 1
                if atty.role:
                    attorney_counts[name_key]["roles"].add(atty.role)
                if atty.firm:
                    attorney_counts[name_key]["firms"].add(atty.firm)
                attorney_counts[name_key]["sources"].add(atty.source)
            
            unique_attorneys = [
                {
                    "name": v["name"],
                    "case_count": v["case_count"],
                    "typical_role": list(v["roles"])[0] if v["roles"] else None,
                    "firms": list(v["firms"]) if v["firms"] else [],
                    "data_sources": list(v["sources"])
                }
                for v in sorted(attorney_counts.values(), key=lambda x: x["case_count"], reverse=True)
            ]
            
            return AttorneySearchResponse(
                success=True,
                cases_analyzed=len(results),
                attorneys_found=all_attorneys,
                cases_with_attorneys=cases_with_attorneys,
                unique_attorneys=unique_attorneys,
                query_used=search_query,
                party_filter=party_filter,
                retrieved_at=get_timestamp()
            )
            
        except httpx.HTTPStatusError as e:
            logger.error(f"CourtListener HTTP error: {e.response.status_code}")
            raise HTTPException(status_code=e.response.status_code, detail=str(e))
        except Exception as e:
            logger.error(f"Attorney search failed: {e}")
            raise HTTPException(status_code=500, detail=str(e))

# ============================================================================
# API ENDPOINTS
# ============================================================================

@app.get("/", response_model=Dict[str, Any])
async def root():
    """Root endpoint - API information"""
    return {
        "service": "LegalNav Live API",
        "version": "1.1.0",
        "status": "running",
        "hackathon": "IBM Dev Day: AI Demystified 2026",
        "description": "Real-time legal data API with attorney extraction",
        "endpoints": {
            "documentation": "/docs",
            "health": "/api/v1/health",
            "search_cases": "/api/v1/cases/search",
            "search_with_attorneys": "/api/v1/cases/search-with-attorneys",
            "verify_attorney": "/api/v1/attorneys/verify"
        },
        "timestamp": get_timestamp()
    }

@app.get("/api/v1/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint"""
    return HealthResponse(
        status="healthy",
        service="LegalNav Live API",
        version="1.1.0",
        timestamp=get_timestamp(),
        courtlistener_configured=bool(COURTLISTENER_API_TOKEN)
    )

@app.post("/api/v1/cases/search", response_model=CaseSearchResponse)
async def search_cases(request: CaseSearchRequest):
    """
    Search CourtListener for relevant case law and legal precedents.
    """
    return await search_courtlistener(
        query=request.query,
        jurisdiction=request.jurisdiction,
        date_after=request.date_after,
        limit=request.limit
    )

@app.post("/api/v1/cases/search-with-attorneys", response_model=AttorneySearchResponse)
async def search_cases_with_attorneys(request: CaseSearchWithAttorneysRequest):
    """
    Search cases AND extract attorney information from each result.
    
    This endpoint:
    1. Searches CourtListener for matching cases
    2. For each case, extracts attorney names from:
       - The search result's attorney field (if available)
       - The docket's parties/attorneys data (for federal cases)
       - The opinion text itself (for state appellate cases)
    3. Returns a list of attorneys who handled similar cases
    
    **Use this to find lawyers who have won cases like yours!**
    
    **Party Filter Options:**
    - `tenant` - Attorneys who represented tenants (appellants/plaintiffs in eviction cases)
    - `appellant` - Attorneys for the appealing party
    - `plaintiff` - Attorneys for plaintiffs
    - `defendant` / `appellee` - Attorneys for defendants/appellees
    - `all` - All attorneys from all parties
    
    **Example:**
    Search for "retaliatory eviction tenant" with party_filter="tenant" to find
    attorneys who successfully represented tenants in retaliation cases.
    """
    return await search_with_attorney_extraction(
        query=request.query,
        jurisdiction=request.jurisdiction,
        date_after=request.date_after,
        party_filter=request.party_type,
        limit=request.limit
    )

@app.post("/api/v1/attorneys/verify", response_model=VerifyAttorneyResponse)
async def verify_attorney(request: VerifyAttorneyRequest):
    """Get verification information for an attorney's bar status."""
    state = request.state.upper()
    bar_number = request.bar_number.strip()
    
    if state not in STATE_BAR_INFO:
        raise HTTPException(status_code=400, detail=f"Invalid state code: {state}")
    
    info = STATE_BAR_INFO[state]
    verification_url = build_verification_url(state, bar_number)
    
    return VerifyAttorneyResponse(
        success=True,
        verified=None,
        status="Verification URL provided - please check directly with state bar",
        name=None,
        admission_date=None,
        discipline_history=False,
        verification_url=verification_url,
        state_bar_name=info["name"],
        instructions=info["instructions"],
        retrieved_at=get_timestamp()
    )

@app.get("/api/v1/jurisdictions", response_model=Dict[str, Any])
async def list_jurisdictions():
    """List available court jurisdictions for case search."""
    return {
        "jurisdictions": {code: {"court_ids": ids} for code, ids in COURTLISTENER_JURISDICTIONS.items()},
        "common": {
            "scotus": "United States Supreme Court",
            "federal": "All Federal Circuit Courts",
            "ca": "California State Courts",
            "tx": "Texas State Courts",
            "ny": "New York State Courts"
        }
    }

@app.get("/api/v1/states", response_model=Dict[str, Any])
async def list_states():
    """List all supported states for attorney verification."""
    return {
        "states": {code: {"name": info["name"], "url": info["url"]} for code, info in STATE_BAR_INFO.items()},
        "total": len(STATE_BAR_INFO)
    }

# ============================================================================
# ERROR HANDLERS
# ============================================================================

@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc):
    return JSONResponse(
        status_code=exc.status_code,
        content={"success": False, "error": exc.detail, "error_code": f"HTTP_{exc.status_code}", "timestamp": get_timestamp()}
    )

@app.exception_handler(Exception)
async def general_exception_handler(request, exc):
    logger.error(f"Unexpected error: {exc}")
    return JSONResponse(
        status_code=500,
        content={"success": False, "error": "An unexpected error occurred", "error_code": "INTERNAL_ERROR", "timestamp": get_timestamp()}
    )

# ============================================================================
# MAIN
# ============================================================================

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=os.getenv("ENVIRONMENT") == "development")














# """
# LegalNav Live API
# =================
# Real-time legal data integration for IBM watsonx Orchestrate
# IBM Dev Day: AI Demystified Hackathon 2026

# This API provides:
# 1. Case Law Search via CourtListener (Free Law Project)
# 2. Attorney Bar Status Verification URLs

# Deploy to: Railway (recommended), Render, or any container platform
# """

# from fastapi import FastAPI, HTTPException, Query
# from fastapi.middleware.cors import CORSMiddleware
# from fastapi.responses import JSONResponse
# from pydantic import BaseModel, Field
# from typing import Optional, List, Dict, Any
# from datetime import datetime
# from enum import Enum
# import httpx
# import os
# import logging

# # ============================================================================
# # LOGGING CONFIGURATION
# # ============================================================================

# logging.basicConfig(
#     level=logging.INFO,
#     format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
# )
# logger = logging.getLogger("legalnav-api")

# # ============================================================================
# # FASTAPI APP SETUP
# # ============================================================================

# app = FastAPI(
#     title="LegalNav Live API",
#     description="""
# ## Real-time Legal Data API for IBM watsonx Orchestrate

# This API powers the LegalNav multi-agent system, providing:

# ### 🔍 Case Law Search
# Search millions of court opinions via CourtListener (Free Law Project).
# Find relevant precedents for tenant rights, employment disputes, family law, and more.

# ### ✅ Attorney Verification
# Get direct links to official state bar verification pages.
# Verify attorney credentials before making recommendations.

# ### 🏛️ Built for IBM Dev Day: AI Demystified Hackathon 2026

# **Data Sources:**
# - CourtListener API (Free Law Project) - 8+ million court opinions
# - State Bar Association websites - All 50 states + DC

# **Note:** This API provides legal information, not legal advice.
#     """,
#     version="1.0.0",
#     docs_url="/docs",
#     redoc_url="/redoc",
#     contact={
#         "name": "LegalNav Team",
#         "url": "https://github.com/your-team/legalnav"
#     },
#     license_info={
#         "name": "MIT License"
#     }
# )

# # CORS Middleware - Allow all origins for hackathon demo
# app.add_middleware(
#     CORSMiddleware,
#     allow_origins=["*"],
#     allow_credentials=True,
#     allow_methods=["*"],
#     allow_headers=["*"],
# )

# # ============================================================================
# # CONFIGURATION
# # ============================================================================

# # CourtListener API Token (optional but recommended for higher rate limits)
# # Get your free token at: https://www.courtlistener.com/help/api/rest/
# COURTLISTENER_API_TOKEN = os.getenv("COURTLISTENER_API_TOKEN", "")

# # Request timeout in seconds
# REQUEST_TIMEOUT = 30.0

# # ============================================================================
# # ENUMS
# # ============================================================================

# class USState(str, Enum):
#     """US State codes for attorney verification"""
#     AL = "AL"
#     AK = "AK"
#     AZ = "AZ"
#     AR = "AR"
#     CA = "CA"
#     CO = "CO"
#     CT = "CT"
#     DE = "DE"
#     DC = "DC"
#     FL = "FL"
#     GA = "GA"
#     HI = "HI"
#     ID = "ID"
#     IL = "IL"
#     IN = "IN"
#     IA = "IA"
#     KS = "KS"
#     KY = "KY"
#     LA = "LA"
#     ME = "ME"
#     MD = "MD"
#     MA = "MA"
#     MI = "MI"
#     MN = "MN"
#     MS = "MS"
#     MO = "MO"
#     MT = "MT"
#     NE = "NE"
#     NV = "NV"
#     NH = "NH"
#     NJ = "NJ"
#     NM = "NM"
#     NY = "NY"
#     NC = "NC"
#     ND = "ND"
#     OH = "OH"
#     OK = "OK"
#     OR = "OR"
#     PA = "PA"
#     RI = "RI"
#     SC = "SC"
#     SD = "SD"
#     TN = "TN"
#     TX = "TX"
#     UT = "UT"
#     VT = "VT"
#     VA = "VA"
#     WA = "WA"
#     WV = "WV"
#     WI = "WI"
#     WY = "WY"

# # ============================================================================
# # PYDANTIC MODELS - REQUEST
# # ============================================================================

# class CaseSearchRequest(BaseModel):
#     """Request model for case law search"""
#     query: str = Field(
#         ...,
#         min_length=3,
#         max_length=500,
#         description="Search terms describing the legal issue. Use specific legal concepts.",
#         examples=["tenant eviction habitability warranty", "wrongful termination whistleblower"]
#     )
#     jurisdiction: Optional[str] = Field(
#         None,
#         min_length=2,
#         max_length=10,
#         description="Court jurisdiction code (e.g., 'ca' for California, 'scotus' for Supreme Court)",
#         examples=["ca", "ny", "tex", "scotus"]
#     )
#     date_after: Optional[str] = Field(
#         None,
#         pattern=r"^\d{4}-\d{2}-\d{2}$",
#         description="Only return cases filed after this date (YYYY-MM-DD format)",
#         examples=["2020-01-01", "2023-06-15"]
#     )
#     limit: int = Field(
#         default=5,
#         ge=1,
#         le=20,
#         description="Maximum number of results to return (1-20)"
#     )

#     class Config:
#         json_schema_extra = {
#             "example": {
#                 "query": "tenant eviction habitability",
#                 "jurisdiction": "ca",
#                 "date_after": "2020-01-01",
#                 "limit": 5
#             }
#         }

# class VerifyAttorneyRequest(BaseModel):
#     """Request model for attorney bar verification"""
#     state: str = Field(
#         ...,
#         min_length=2,
#         max_length=2,
#         description="Two-letter US state code (uppercase)",
#         examples=["CA", "TX", "NY", "FL"]
#     )
#     bar_number: str = Field(
#         ...,
#         min_length=1,
#         max_length=20,
#         description="Attorney's bar number as issued by the state bar",
#         examples=["123456", "TX12345678"]
#     )

#     class Config:
#         json_schema_extra = {
#             "example": {
#                 "state": "CA",
#                 "bar_number": "123456"
#             }
#         }

# # ============================================================================
# # PYDANTIC MODELS - RESPONSE
# # ============================================================================

# class CaseResult(BaseModel):
#     """Individual case result from search"""
#     case_name: str = Field(..., description="Full case name (e.g., 'Smith v. Jones')")
#     citation: Optional[str] = Field(None, description="Official legal citation if available")
#     date_filed: str = Field(..., description="Date the case was filed or decided")
#     court: str = Field(..., description="Name of the court")
#     court_id: Optional[str] = Field(None, description="CourtListener court identifier")
#     summary: Optional[str] = Field(None, description="Brief excerpt from the opinion")
#     url: str = Field(..., description="Link to read the full opinion on CourtListener")

# class CaseSearchResponse(BaseModel):
#     """Response model for case law search"""
#     success: bool = Field(True, description="Whether the search was successful")
#     cases: List[CaseResult] = Field(default_factory=list, description="List of matching cases")
#     total_results: int = Field(0, description="Total matching cases (may exceed limit)")
#     query_used: str = Field(..., description="The search query that was executed")
#     source: str = Field("CourtListener (Free Law Project)", description="Data source attribution")
#     source_url: str = Field("https://www.courtlistener.com", description="Link to data source")
#     retrieved_at: str = Field(..., description="ISO timestamp of when search was performed")
#     disclaimer: str = Field(
#         "This is legal information, not legal advice. Case law interpretation varies by jurisdiction and circumstances.",
#         description="Legal disclaimer"
#     )

# class VerifyAttorneyResponse(BaseModel):
#     """Response model for attorney verification"""
#     success: bool = Field(True, description="Whether the lookup was successful")
#     verified: Optional[bool] = Field(None, description="Verification status (null = manual check required)")
#     status: str = Field(..., description="Status message")
#     name: Optional[str] = Field(None, description="Attorney's name if available")
#     admission_date: Optional[str] = Field(None, description="Bar admission date if available")
#     discipline_history: bool = Field(False, description="Whether disciplinary records exist")
#     verification_url: str = Field(..., description="URL to verify attorney credentials")
#     state_bar_name: str = Field(..., description="Name of the state bar association")
#     instructions: str = Field(..., description="Instructions for verification")
#     retrieved_at: str = Field(..., description="ISO timestamp")

# class HealthResponse(BaseModel):
#     """Response model for health check"""
#     status: str = Field(..., description="API health status")
#     service: str = Field(..., description="Service name")
#     version: str = Field(..., description="API version")
#     timestamp: str = Field(..., description="Current timestamp")
#     courtlistener_configured: bool = Field(..., description="Whether CourtListener token is set")

# class ErrorResponse(BaseModel):
#     """Error response model"""
#     success: bool = Field(False)
#     error: str = Field(..., description="Error message")
#     error_code: str = Field(..., description="Error code")
#     timestamp: str = Field(..., description="When the error occurred")

# # ============================================================================
# # STATE BAR INFORMATION
# # ============================================================================

# STATE_BAR_INFO = {
#     "AL": {"name": "Alabama State Bar", "url": "https://www.alabar.org/for-the-public/find-a-lawyer/", "instructions": "Search by name or bar number"},
#     "AK": {"name": "Alaska Bar Association", "url": "https://www.alaskabar.org/attorney-directory/", "instructions": "Search by name or bar number"},
#     "AZ": {"name": "State Bar of Arizona", "url": "https://www.azbar.org/for-the-public/find-a-lawyer/", "instructions": "Search by name or bar number"},
#     "AR": {"name": "Arkansas Bar Association", "url": "https://www.arkbar.com/for-the-public/lawyer-search", "instructions": "Search by name"},
#     "CA": {"name": "State Bar of California", "url": "https://apps.calbar.ca.gov/attorney/Licensee/Detail/", "instructions": "Add the bar number to the end of the URL, or search at calbar.ca.gov"},
#     "CO": {"name": "Colorado Supreme Court Office of Attorney Regulation", "url": "https://www.coloradosupremecourt.com/Search/AttSearch.asp", "instructions": "Search by name or registration number"},
#     "CT": {"name": "Connecticut Bar Association", "url": "https://www.jud.ct.gov/attorneyfirminquiry/", "instructions": "Search by name or juris number"},
#     "DE": {"name": "Delaware State Bar Association", "url": "https://courts.delaware.gov/forms/download.aspx?id=39492", "instructions": "Search by name"},
#     "DC": {"name": "District of Columbia Bar", "url": "https://www.dcbar.org/membership/members", "instructions": "Search by name or bar number"},
#     "FL": {"name": "The Florida Bar", "url": "https://www.floridabar.org/directories/find-mbr/", "instructions": "Search by name or bar number"},
#     "GA": {"name": "State Bar of Georgia", "url": "https://www.gabar.org/membersearchresults.cfm", "instructions": "Search by name or bar number"},
#     "HI": {"name": "Hawaii State Bar Association", "url": "https://hsba.org/HSBA/For_the_Public/Find_a_Lawyer/HSBA/FOR_THE_PUBLIC/Find_a_Lawyer.aspx", "instructions": "Search by name"},
#     "ID": {"name": "Idaho State Bar", "url": "https://isb.idaho.gov/licensing/attorney-roster/", "instructions": "Search by name"},
#     "IL": {"name": "ARDC Illinois", "url": "https://www.iardc.org/lawyersearch.asp", "instructions": "Search by name or registration number"},
#     "IN": {"name": "Indiana Supreme Court Roll of Attorneys", "url": "https://courtapps.in.gov/rollofattorneys/", "instructions": "Search by name or attorney number"},
#     "IA": {"name": "Iowa Judicial Branch", "url": "https://www.iacourtcommissions.org/iowaattorney/attorney.do", "instructions": "Search by name or bar number"},
#     "KS": {"name": "Kansas Bar Association", "url": "https://www.kscourts.org/attorney", "instructions": "Search by name or bar number"},
#     "KY": {"name": "Kentucky Bar Association", "url": "https://www.kybar.org/search/custom.asp?id=2972", "instructions": "Search by name or bar number"},
#     "LA": {"name": "Louisiana State Bar Association", "url": "https://www.lsba.org/Public/FindLawyer.aspx", "instructions": "Search by name or bar number"},
#     "ME": {"name": "Maine Board of Overseers of the Bar", "url": "https://www.mebaroverseers.org/attorney_search.html", "instructions": "Search by name or bar number"},
#     "MD": {"name": "Maryland Courts Attorney Search", "url": "https://mdcourts.gov/attygrievance/attorneysearch", "instructions": "Search by name or ID"},
#     "MA": {"name": "Massachusetts Board of Bar Overseers", "url": "https://www.massbbo.org/AttorneySearch", "instructions": "Search by name or BBO number"},
#     "MI": {"name": "State Bar of Michigan", "url": "https://www.michbar.org/member/MemberDirectory", "instructions": "Search by name or P number"},
#     "MN": {"name": "Minnesota Lawyer Registration", "url": "https://www.mncourts.gov/Find-a-Lawyer.aspx", "instructions": "Search by name or ID"},
#     "MS": {"name": "Mississippi Bar", "url": "https://www.msbar.org/for-the-public/attorney-directory/", "instructions": "Search by name or bar number"},
#     "MO": {"name": "Missouri Bar", "url": "https://mobar.org/public/AttorneyDirectorySearch.aspx", "instructions": "Search by name or bar number"},
#     "MT": {"name": "State Bar of Montana", "url": "https://www.montanabar.org/page/FindLegalHelp", "instructions": "Search by name"},
#     "NE": {"name": "Nebraska State Bar Association", "url": "https://www.nebar.com/search/custom.asp?id=2040", "instructions": "Search by name"},
#     "NV": {"name": "State Bar of Nevada", "url": "https://nvbar.org/member-services/member-directory/", "instructions": "Search by name or bar number"},
#     "NH": {"name": "New Hampshire Bar Association", "url": "https://www.nhbar.org/lawyer-referral-service/", "instructions": "Search by name"},
#     "NJ": {"name": "New Jersey Courts Attorney Search", "url": "https://portal.njcourts.gov/webcivilcj/CJWebApp/pages/showAttorneyInfo.faces", "instructions": "Search by name or ID"},
#     "NM": {"name": "State Bar of New Mexico", "url": "https://www.sbnm.org/For-Public/Find-A-Lawyer", "instructions": "Search by name"},
#     "NY": {"name": "New York Courts Attorney Search", "url": "https://iapps.courts.state.ny.us/attorneyservices/search", "instructions": "Search by name or registration number"},
#     "NC": {"name": "North Carolina State Bar", "url": "https://www.ncbar.gov/for-the-public/find-a-lawyer/", "instructions": "Search by name or bar number"},
#     "ND": {"name": "State Bar Association of North Dakota", "url": "https://www.sband.org/search/custom.asp?id=5512", "instructions": "Search by name"},
#     "OH": {"name": "Ohio Supreme Court Attorney Directory", "url": "https://www.supremecourt.ohio.gov/AttorneySearch/", "instructions": "Search by name or registration number"},
#     "OK": {"name": "Oklahoma Bar Association", "url": "https://www.okbar.org/freelegalinfo/findingalawyer/", "instructions": "Search by name or bar number"},
#     "OR": {"name": "Oregon State Bar", "url": "https://www.osbar.org/members/membersearch.asp", "instructions": "Search by name or bar number"},
#     "PA": {"name": "Pennsylvania Bar Association", "url": "https://www.padisciplinaryboard.org/for-the-public/find-attorney", "instructions": "Search by name or ID"},
#     "RI": {"name": "Rhode Island Bar Association", "url": "https://www.ribar.com/for-the-public/find-a-lawyer/", "instructions": "Search by name"},
#     "SC": {"name": "South Carolina Bar", "url": "https://www.scbar.org/lawyers/lawyer-directory/", "instructions": "Search by name or bar number"},
#     "SD": {"name": "State Bar of South Dakota", "url": "https://www.statebarofsouthdakota.com/find-a-lawyer", "instructions": "Search by name"},
#     "TN": {"name": "Tennessee Board of Professional Responsibility", "url": "https://www.tbpr.org/attorneys", "instructions": "Search by name or BPR number"},
#     "TX": {"name": "State Bar of Texas", "url": "https://www.texasbar.com/AM/Template.cfm?Section=Find_A_Lawyer", "instructions": "Search by name or bar number"},
#     "UT": {"name": "Utah State Bar", "url": "https://www.utahbar.org/public-services/find-a-lawyer/", "instructions": "Search by name or bar number"},
#     "VT": {"name": "Vermont Bar Association", "url": "https://www.vtbar.org/find-a-lawyer/", "instructions": "Search by name"},
#     "VA": {"name": "Virginia State Bar", "url": "https://www.vsb.org/attorney/attSearch.asp", "instructions": "Search by name or VSB number"},
#     "WA": {"name": "Washington State Bar Association", "url": "https://www.mywsba.org/PersonifyEbusiness/LegalDirectory.aspx", "instructions": "Search by name or bar number"},
#     "WV": {"name": "West Virginia State Bar", "url": "https://wvbar.org/for-the-public/find-a-lawyer/", "instructions": "Search by name"},
#     "WI": {"name": "State Bar of Wisconsin", "url": "https://www.wisbar.org/forPublic/FindaLawyer/Pages/Find-a-Lawyer.aspx", "instructions": "Search by name or bar number"},
#     "WY": {"name": "Wyoming State Bar", "url": "https://www.wyomingbar.org/for-the-public/find-a-lawyer/", "instructions": "Search by name"}
# }

# # ============================================================================
# # COURTLISTENER JURISDICTIONS - Updated for Search API court_id syntax
# # ============================================================================

# # These are the court_id values that work with CourtListener's Search API
# # For multiple courts, we'll use OR syntax in the query: (court_id:cal OR court_id:calctapp)
# COURTLISTENER_JURISDICTIONS = {
#     "ca": ["cal", "calctapp", "calappdeptsuperct"],
#     "tx": ["tex", "texapp", "texcrimapp"],
#     "ny": ["ny", "nyappdiv", "nyappterm"],
#     "fl": ["fla", "fladistctapp"],
#     "il": ["ill", "illappct"],
#     "pa": ["pa", "pasuperct", "pacommwct"],
#     "oh": ["ohio", "ohioctapp"],
#     "ga": ["ga", "gactapp"],
#     "nc": ["nc", "ncctapp"],
#     "nj": ["nj", "njsuperctappdiv"],
#     "mi": ["mich", "michctapp"],
#     "va": ["va", "vactapp"],
#     "wa": ["wash", "washctapp"],
#     "az": ["ariz", "arizctapp"],
#     "ma": ["mass", "massappct"],
#     "in": ["ind", "indctapp"],
#     "tn": ["tenn", "tennctapp"],
#     "mo": ["mo", "moctapp"],
#     "md": ["md", "mdctspecapp"],
#     "wi": ["wis", "wisctapp"],
#     "co": ["colo", "coloctapp"],
#     "mn": ["minn", "minnctapp"],
#     "al": ["ala", "alactapp"],
#     "sc": ["sc", "scctapp"],
#     "la": ["la", "lactapp"],
#     "ky": ["ky", "kyctapp"],
#     "or": ["or", "orctapp"],
#     "ok": ["okla", "oklacivapp", "oklacrimapp"],
#     "ct": ["conn", "connappct"],
#     "ia": ["iowa", "iowactapp"],
#     "ms": ["miss", "missctapp"],
#     "ar": ["ark", "arkctapp"],
#     "ks": ["kan", "kanctapp"],
#     "ut": ["utah", "utahctapp"],
#     "nv": ["nev", "nevapp"],
#     "nm": ["nm", "nmctapp"],
#     "ne": ["neb", "nebctapp"],
#     "wv": ["wva"],
#     "id": ["idaho", "idahoctapp"],
#     "hi": ["haw", "hawapp"],
#     "me": ["me"],
#     "nh": ["nh"],
#     "ri": ["ri"],
#     "mt": ["mont"],
#     "de": ["del", "delch", "delsuperct"],
#     "sd": ["sd"],
#     "nd": ["nd", "ndctapp"],
#     "ak": ["alaska", "alaskactapp"],
#     "dc": ["dc", "dcctapp"],
#     "vt": ["vt"],
#     "wy": ["wyo"],
#     "scotus": ["scotus"],
#     "federal": ["ca1", "ca2", "ca3", "ca4", "ca5", "ca6", "ca7", "ca8", "ca9", "ca10", "ca11", "cadc", "cafc"]
# }

# # ============================================================================
# # HELPER FUNCTIONS
# # ============================================================================

# def get_timestamp() -> str:
#     """Get current UTC timestamp in ISO format"""
#     return datetime.utcnow().isoformat() + "Z"

# def get_state_bar_info(state: str) -> Dict[str, str]:
#     """Get state bar information for a given state code"""
#     state = state.upper()
#     if state in STATE_BAR_INFO:
#         return STATE_BAR_INFO[state]
#     return {
#         "name": f"{state} State Bar",
#         "url": "https://www.americanbar.org/groups/legal_services/flh-home/",
#         "instructions": "Visit the American Bar Association to find your state bar"
#     }

# def build_verification_url(state: str, bar_number: str) -> str:
#     """Build the verification URL for a state, with direct linking if available"""
#     state = state.upper()
#     info = STATE_BAR_INFO.get(state, {})
    
#     # California supports direct linking
#     if state == "CA" and bar_number:
#         return f"https://apps.calbar.ca.gov/attorney/Licensee/Detail/{bar_number}"
    
#     # Return base URL for other states
#     return info.get("url", "https://www.americanbar.org/groups/legal_services/flh-home/")

# def build_court_filter_query(jurisdiction: str) -> str:
#     """
#     Build court filter query string for CourtListener Search API.
    
#     The Search API uses court_id: syntax in the query, not a separate parameter.
#     For multiple courts, we use OR syntax: (court_id:cal OR court_id:calctapp)
#     """
#     jurisdiction = jurisdiction.lower()
    
#     if jurisdiction in COURTLISTENER_JURISDICTIONS:
#         court_ids = COURTLISTENER_JURISDICTIONS[jurisdiction]
#         if len(court_ids) == 1:
#             return f"court_id:{court_ids[0]}"
#         else:
#             # Build OR query for multiple courts
#             court_clauses = [f"court_id:{cid}" for cid in court_ids]
#             return "(" + " OR ".join(court_clauses) + ")"
#     else:
#         # If not in our mapping, try using it directly as a court_id
#         return f"court_id:{jurisdiction}"

# # ============================================================================
# # COURTLISTENER API INTEGRATION
# # ============================================================================

# async def search_courtlistener(
#     query: str,
#     jurisdiction: Optional[str] = None,
#     date_after: Optional[str] = None,
#     limit: int = 5
# ) -> CaseSearchResponse:
#     """
#     Search CourtListener for case law
    
#     CourtListener API Docs: https://www.courtlistener.com/help/api/rest/
    
#     IMPORTANT: The Search API (/api/rest/v4/search/) uses court_id: in the query,
#     NOT a separate 'court' parameter. This is different from the database APIs.
#     """
    
#     base_url = "https://www.courtlistener.com/api/rest/v4/search/"
    
#     # Build the search query with jurisdiction filter embedded
#     search_query = query
#     if jurisdiction:
#         court_filter = build_court_filter_query(jurisdiction)
#         search_query = f"{query} {court_filter}"
    
#     # Build search parameters
#     params = {
#         "q": search_query,
#         "type": "o",  # Search opinions
#         "order_by": "score desc",
#         "page_size": min(limit, 20)
#     }
    
#     # Add date filter if provided
#     if date_after:
#         params["filed_after"] = date_after
    
#     # Build headers
#     headers = {
#         "User-Agent": "LegalNav-API/1.0 (IBM-DevDay-Hackathon)"
#     }
#     if COURTLISTENER_API_TOKEN:
#         headers["Authorization"] = f"Token {COURTLISTENER_API_TOKEN}"
    
#     logger.info(f"Searching CourtListener: query='{search_query}', limit={limit}")
    
#     async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
#         try:
#             response = await client.get(base_url, params=params, headers=headers)
#             response.raise_for_status()
#             data = response.json()
            
#             cases = []
#             for result in data.get("results", [])[:limit]:
#                 # Extract citation (can be a list)
#                 citations = result.get("citation", [])
#                 citation = None
#                 if isinstance(citations, list) and citations:
#                     citation = citations[0]
#                 elif isinstance(citations, str):
#                     citation = citations
                
#                 # Extract snippet/summary
#                 snippet = result.get("snippet", "")
#                 if snippet:
#                     # Clean up HTML tags from snippet
#                     snippet = snippet.replace("<mark>", "**").replace("</mark>", "**")
#                     snippet = snippet[:500] + "..." if len(snippet) > 500 else snippet
                
#                 # Build absolute URL
#                 absolute_url = result.get("absolute_url", "")
#                 if absolute_url and not absolute_url.startswith("http"):
#                     absolute_url = f"https://www.courtlistener.com{absolute_url}"
#                 elif not absolute_url:
#                     cluster_id = result.get("cluster_id", "")
#                     if cluster_id:
#                         absolute_url = f"https://www.courtlistener.com/opinion/{cluster_id}/"
                
#                 cases.append(CaseResult(
#                     case_name=result.get("caseName", result.get("case_name", "Unknown Case")),
#                     citation=citation,
#                     date_filed=result.get("dateFiled", result.get("date_filed", "Unknown")),
#                     court=result.get("court", result.get("court_id", "Unknown Court")),
#                     court_id=result.get("court_id"),
#                     summary=snippet if snippet else None,
#                     url=absolute_url if absolute_url else "https://www.courtlistener.com"
#                 ))
            
#             logger.info(f"Found {len(cases)} cases out of {data.get('count', 0)} total")
            
#             return CaseSearchResponse(
#                 success=True,
#                 cases=cases,
#                 total_results=data.get("count", 0),
#                 query_used=search_query,
#                 source="CourtListener (Free Law Project)",
#                 source_url="https://www.courtlistener.com",
#                 retrieved_at=get_timestamp()
#             )
            
#         except httpx.HTTPStatusError as e:
#             logger.error(f"CourtListener HTTP error: {e.response.status_code} - {e.response.text}")
#             raise HTTPException(
#                 status_code=e.response.status_code,
#                 detail=f"CourtListener API error: {e.response.text}"
#             )
#         except httpx.TimeoutException:
#             logger.error("CourtListener request timed out")
#             raise HTTPException(
#                 status_code=504,
#                 detail="Search request timed out. Please try again with a simpler query."
#             )
#         except Exception as e:
#             logger.error(f"CourtListener search failed: {str(e)}")
#             raise HTTPException(
#                 status_code=500,
#                 detail=f"Search failed: {str(e)}"
#             )

# # ============================================================================
# # API ENDPOINTS
# # ============================================================================

# @app.get("/", response_model=Dict[str, Any])
# async def root():
#     """
#     Root endpoint - API information and health check
    
#     Returns basic information about the LegalNav API including
#     available endpoints and service status.
#     """
#     return {
#         "service": "LegalNav Live API",
#         "version": "1.0.0",
#         "status": "running",
#         "hackathon": "IBM Dev Day: AI Demystified 2026",
#         "description": "Real-time legal data API for watsonx Orchestrate",
#         "endpoints": {
#             "documentation": "/docs",
#             "health": "/api/v1/health",
#             "search_cases": "/api/v1/cases/search",
#             "verify_attorney": "/api/v1/attorneys/verify"
#         },
#         "data_sources": {
#             "case_law": "CourtListener (Free Law Project)",
#             "attorney_verification": "State Bar Associations"
#         },
#         "timestamp": get_timestamp()
#     }

# @app.get("/api/v1/health", response_model=HealthResponse)
# async def health_check():
#     """
#     Health check endpoint
    
#     Returns the current status of the API including whether
#     external service credentials are configured.
#     """
#     return HealthResponse(
#         status="healthy",
#         service="LegalNav Live API",
#         version="1.0.0",
#         timestamp=get_timestamp(),
#         courtlistener_configured=bool(COURTLISTENER_API_TOKEN)
#     )

# @app.post(
#     "/api/v1/cases/search",
#     response_model=CaseSearchResponse,
#     responses={
#         400: {"model": ErrorResponse, "description": "Invalid request parameters"},
#         500: {"model": ErrorResponse, "description": "Server error"},
#         504: {"model": ErrorResponse, "description": "Request timeout"}
#     }
# )
# async def search_cases(request: CaseSearchRequest):
#     """
#     Search CourtListener for relevant case law and legal precedents.
    
#     This endpoint searches the CourtListener database (Free Law Project),
#     which contains over 8 million court opinions from federal and state courts.
    
#     **Use Cases:**
#     - Find cases related to tenant rights, evictions, habitability
#     - Research employment law precedents
#     - Find family law cases about custody, support
#     - Search for civil rights cases
#     - Research consumer protection cases
    
#     **Tips for Better Results:**
#     - Use specific legal terms (e.g., "implied warranty habitability" not "apartment problems")
#     - Add jurisdiction for state-specific results
#     - Use date filters for recent precedents
    
#     **Example Queries:**
#     - "tenant eviction retaliatory habitability"
#     - "wrongful termination whistleblower at-will employment"
#     - "custody modification best interest child"
#     - "wage theft unpaid overtime FLSA"
#     """
#     return await search_courtlistener(
#         query=request.query,
#         jurisdiction=request.jurisdiction,
#         date_after=request.date_after,
#         limit=request.limit
#     )

# @app.post(
#     "/api/v1/attorneys/verify",
#     response_model=VerifyAttorneyResponse,
#     responses={
#         400: {"model": ErrorResponse, "description": "Invalid state code or bar number"}
#     }
# )
# async def verify_attorney(request: VerifyAttorneyRequest):
#     """
#     Get verification information for an attorney's bar status.
    
#     Returns the official state bar verification URL where users can
#     confirm an attorney's current license status and standing.
    
#     **What This Returns:**
#     - Direct link to official state bar verification page
#     - Instructions on how to verify
#     - State bar contact information
    
#     **Supported for All 50 States + DC**
    
#     **Note:** For privacy and accuracy, users should verify directly
#     with the state bar using the provided URL rather than relying
#     on cached or third-party data.
#     """
#     state = request.state.upper()
#     bar_number = request.bar_number.strip()
    
#     # Validate state code
#     if state not in STATE_BAR_INFO:
#         raise HTTPException(
#             status_code=400,
#             detail=f"Invalid state code: {state}. Use two-letter state codes (e.g., CA, TX, NY)."
#         )
    
#     info = STATE_BAR_INFO[state]
#     verification_url = build_verification_url(state, bar_number)
    
#     logger.info(f"Attorney verification request: state={state}, bar_number={bar_number}")
    
#     return VerifyAttorneyResponse(
#         success=True,
#         verified=None,  # Manual verification required
#         status="Verification URL provided - please check directly with state bar",
#         name=None,
#         admission_date=None,
#         discipline_history=False,
#         verification_url=verification_url,
#         state_bar_name=info["name"],
#         instructions=info["instructions"],
#         retrieved_at=get_timestamp()
#     )

# # ============================================================================
# # ADDITIONAL ENDPOINTS FOR WATSONX ORCHESTRATE
# # ============================================================================

# @app.get(
#     "/api/v1/jurisdictions",
#     response_model=Dict[str, Any]
# )
# async def list_jurisdictions():
#     """
#     List available court jurisdictions for case search.
    
#     Returns a mapping of jurisdiction codes that can be used
#     with the case search endpoint.
#     """
#     return {
#         "jurisdictions": {
#             code: {"court_ids": court_ids}
#             for code, court_ids in COURTLISTENER_JURISDICTIONS.items()
#         },
#         "common": {
#             "scotus": "United States Supreme Court",
#             "federal": "All Federal Circuit Courts",
#             "ca": "California State Courts",
#             "tx": "Texas State Courts",
#             "ny": "New York State Courts",
#             "fl": "Florida State Courts"
#         },
#         "note": "Use lowercase jurisdiction codes in the search request"
#     }

# @app.get(
#     "/api/v1/states",
#     response_model=Dict[str, Any]
# )
# async def list_states():
#     """
#     List all supported states for attorney verification.
    
#     Returns information about all 50 states + DC including
#     their state bar names and verification URLs.
#     """
#     return {
#         "states": {
#             code: {
#                 "name": info["name"],
#                 "verification_url": info["url"]
#             }
#             for code, info in STATE_BAR_INFO.items()
#         },
#         "total": len(STATE_BAR_INFO),
#         "note": "Use uppercase state codes (e.g., CA, TX, NY)"
#     }

# # ============================================================================
# # ERROR HANDLERS
# # ============================================================================

# @app.exception_handler(HTTPException)
# async def http_exception_handler(request, exc):
#     """Handle HTTP exceptions with consistent format"""
#     return JSONResponse(
#         status_code=exc.status_code,
#         content={
#             "success": False,
#             "error": exc.detail,
#             "error_code": f"HTTP_{exc.status_code}",
#             "timestamp": get_timestamp()
#         }
#     )

# @app.exception_handler(Exception)
# async def general_exception_handler(request, exc):
#     """Handle unexpected exceptions"""
#     logger.error(f"Unexpected error: {str(exc)}")
#     return JSONResponse(
#         status_code=500,
#         content={
#             "success": False,
#             "error": "An unexpected error occurred",
#             "error_code": "INTERNAL_ERROR",
#             "timestamp": get_timestamp()
#         }
#     )

# # ============================================================================
# # MAIN ENTRY POINT
# # ============================================================================

# if __name__ == "__main__":
#     import uvicorn
#     port = int(os.getenv("PORT", 8000))
#     uvicorn.run(
#         "main:app",
#         host="0.0.0.0",
#         port=port,
#         reload=os.getenv("ENVIRONMENT", "production") == "development"
#     )













# # """
# # LegalNav Live API
# # =================
# # Real-time legal data integration for IBM watsonx Orchestrate
# # IBM Dev Day: AI Demystified Hackathon 2026

# # This API provides:
# # 1. Case Law Search via CourtListener (Free Law Project)
# # 2. Attorney Bar Status Verification URLs

# # Deploy to: Railway (recommended), Render, or any container platform
# # """

# # from fastapi import FastAPI, HTTPException, Query
# # from fastapi.middleware.cors import CORSMiddleware
# # from fastapi.responses import JSONResponse
# # from pydantic import BaseModel, Field
# # from typing import Optional, List, Dict, Any
# # from datetime import datetime
# # from enum import Enum
# # import httpx
# # import os
# # import logging

# # # ============================================================================
# # # LOGGING CONFIGURATION
# # # ============================================================================

# # logging.basicConfig(
# #     level=logging.INFO,
# #     format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
# # )
# # logger = logging.getLogger("legalnav-api")

# # # ============================================================================
# # # FASTAPI APP SETUP
# # # ============================================================================

# # app = FastAPI(
# #     title="LegalNav Live API",
# #     description="""
# # ## Real-time Legal Data API for IBM watsonx Orchestrate

# # This API powers the LegalNav multi-agent system, providing:

# # ### 🔍 Case Law Search
# # Search millions of court opinions via CourtListener (Free Law Project).
# # Find relevant precedents for tenant rights, employment disputes, family law, and more.

# # ### ✅ Attorney Verification
# # Get direct links to official state bar verification pages.
# # Verify attorney credentials before making recommendations.

# # ### 🏛️ Built for IBM Dev Day: AI Demystified Hackathon 2026

# # **Data Sources:**
# # - CourtListener API (Free Law Project) - 8+ million court opinions
# # - State Bar Association websites - All 50 states + DC

# # **Note:** This API provides legal information, not legal advice.
# #     """,
# #     version="1.0.0",
# #     docs_url="/docs",
# #     redoc_url="/redoc",
# #     contact={
# #         "name": "LegalNav Team",
# #         "url": "https://github.com/your-team/legalnav"
# #     },
# #     license_info={
# #         "name": "MIT License"
# #     }
# # )

# # # CORS Middleware - Allow all origins for hackathon demo
# # app.add_middleware(
# #     CORSMiddleware,
# #     allow_origins=["*"],
# #     allow_credentials=True,
# #     allow_methods=["*"],
# #     allow_headers=["*"],
# # )

# # # ============================================================================
# # # CONFIGURATION
# # # ============================================================================

# # # CourtListener API Token (optional but recommended for higher rate limits)
# # # Get your free token at: https://www.courtlistener.com/help/api/rest/
# # COURTLISTENER_API_TOKEN = os.getenv("COURTLISTENER_API_TOKEN", "")

# # # Request timeout in seconds
# # REQUEST_TIMEOUT = 30.0

# # # ============================================================================
# # # ENUMS
# # # ============================================================================

# # class USState(str, Enum):
# #     """US State codes for attorney verification"""
# #     AL = "AL"
# #     AK = "AK"
# #     AZ = "AZ"
# #     AR = "AR"
# #     CA = "CA"
# #     CO = "CO"
# #     CT = "CT"
# #     DE = "DE"
# #     DC = "DC"
# #     FL = "FL"
# #     GA = "GA"
# #     HI = "HI"
# #     ID = "ID"
# #     IL = "IL"
# #     IN = "IN"
# #     IA = "IA"
# #     KS = "KS"
# #     KY = "KY"
# #     LA = "LA"
# #     ME = "ME"
# #     MD = "MD"
# #     MA = "MA"
# #     MI = "MI"
# #     MN = "MN"
# #     MS = "MS"
# #     MO = "MO"
# #     MT = "MT"
# #     NE = "NE"
# #     NV = "NV"
# #     NH = "NH"
# #     NJ = "NJ"
# #     NM = "NM"
# #     NY = "NY"
# #     NC = "NC"
# #     ND = "ND"
# #     OH = "OH"
# #     OK = "OK"
# #     OR = "OR"
# #     PA = "PA"
# #     RI = "RI"
# #     SC = "SC"
# #     SD = "SD"
# #     TN = "TN"
# #     TX = "TX"
# #     UT = "UT"
# #     VT = "VT"
# #     VA = "VA"
# #     WA = "WA"
# #     WV = "WV"
# #     WI = "WI"
# #     WY = "WY"

# # # ============================================================================
# # # PYDANTIC MODELS - REQUEST
# # # ============================================================================

# # class CaseSearchRequest(BaseModel):
# #     """Request model for case law search"""
# #     query: str = Field(
# #         ...,
# #         min_length=3,
# #         max_length=500,
# #         description="Search terms describing the legal issue. Use specific legal concepts.",
# #         examples=["tenant eviction habitability warranty", "wrongful termination whistleblower"]
# #     )
# #     jurisdiction: Optional[str] = Field(
# #         None,
# #         min_length=2,
# #         max_length=10,
# #         description="Court jurisdiction code (e.g., 'ca' for California, 'scotus' for Supreme Court)",
# #         examples=["ca", "ny", "tex", "scotus"]
# #     )
# #     date_after: Optional[str] = Field(
# #         None,
# #         pattern=r"^\d{4}-\d{2}-\d{2}$",
# #         description="Only return cases filed after this date (YYYY-MM-DD format)",
# #         examples=["2020-01-01", "2023-06-15"]
# #     )
# #     limit: int = Field(
# #         default=5,
# #         ge=1,
# #         le=20,
# #         description="Maximum number of results to return (1-20)"
# #     )

# #     class Config:
# #         json_schema_extra = {
# #             "example": {
# #                 "query": "tenant eviction habitability",
# #                 "jurisdiction": "ca",
# #                 "date_after": "2020-01-01",
# #                 "limit": 5
# #             }
# #         }

# # class VerifyAttorneyRequest(BaseModel):
# #     """Request model for attorney bar verification"""
# #     state: str = Field(
# #         ...,
# #         min_length=2,
# #         max_length=2,
# #         description="Two-letter US state code (uppercase)",
# #         examples=["CA", "TX", "NY", "FL"]
# #     )
# #     bar_number: str = Field(
# #         ...,
# #         min_length=1,
# #         max_length=20,
# #         description="Attorney's bar number as issued by the state bar",
# #         examples=["123456", "TX12345678"]
# #     )

# #     class Config:
# #         json_schema_extra = {
# #             "example": {
# #                 "state": "CA",
# #                 "bar_number": "123456"
# #             }
# #         }

# # # ============================================================================
# # # PYDANTIC MODELS - RESPONSE
# # # ============================================================================

# # class CaseResult(BaseModel):
# #     """Individual case result from search"""
# #     case_name: str = Field(..., description="Full case name (e.g., 'Smith v. Jones')")
# #     citation: Optional[str] = Field(None, description="Official legal citation if available")
# #     date_filed: str = Field(..., description="Date the case was filed or decided")
# #     court: str = Field(..., description="Name of the court")
# #     court_id: Optional[str] = Field(None, description="CourtListener court identifier")
# #     summary: Optional[str] = Field(None, description="Brief excerpt from the opinion")
# #     url: str = Field(..., description="Link to read the full opinion on CourtListener")

# # class CaseSearchResponse(BaseModel):
# #     """Response model for case law search"""
# #     success: bool = Field(True, description="Whether the search was successful")
# #     cases: List[CaseResult] = Field(default_factory=list, description="List of matching cases")
# #     total_results: int = Field(0, description="Total matching cases (may exceed limit)")
# #     query_used: str = Field(..., description="The search query that was executed")
# #     source: str = Field("CourtListener (Free Law Project)", description="Data source attribution")
# #     source_url: str = Field("https://www.courtlistener.com", description="Link to data source")
# #     retrieved_at: str = Field(..., description="ISO timestamp of when search was performed")
# #     disclaimer: str = Field(
# #         "This is legal information, not legal advice. Case law interpretation varies by jurisdiction and circumstances.",
# #         description="Legal disclaimer"
# #     )

# # class VerifyAttorneyResponse(BaseModel):
# #     """Response model for attorney verification"""
# #     success: bool = Field(True, description="Whether the lookup was successful")
# #     verified: Optional[bool] = Field(
# #         None, 
# #         description="True if verified active, False if inactive/suspended, null if manual check required"
# #     )
# #     status: str = Field(..., description="Current bar status or instruction")
# #     name: Optional[str] = Field(None, description="Attorney's registered name if available")
# #     admission_date: Optional[str] = Field(None, description="Bar admission date if available")
# #     discipline_history: bool = Field(False, description="Whether disciplinary records exist")
# #     verification_url: str = Field(..., description="Official state bar verification URL")
# #     state_bar_name: str = Field(..., description="Name of the state bar association")
# #     instructions: str = Field(..., description="How to use the verification URL")
# #     retrieved_at: str = Field(..., description="ISO timestamp")

# # class HealthResponse(BaseModel):
# #     """Health check response"""
# #     status: str = Field("healthy", description="API health status")
# #     service: str = Field("LegalNav Live API", description="Service name")
# #     version: str = Field("1.0.0", description="API version")
# #     timestamp: str = Field(..., description="Current server time")
# #     courtlistener_configured: bool = Field(..., description="Whether CourtListener token is set")

# # class ErrorResponse(BaseModel):
# #     """Error response model"""
# #     success: bool = Field(False)
# #     error: str = Field(..., description="Error message")
# #     error_code: str = Field(..., description="Error code for debugging")
# #     timestamp: str = Field(..., description="When the error occurred")

# # # ============================================================================
# # # STATE BAR VERIFICATION URLS - COMPREHENSIVE LIST
# # # ============================================================================

# # STATE_BAR_INFO: Dict[str, Dict[str, str]] = {
# #     "AL": {
# #         "name": "Alabama State Bar",
# #         "url": "https://www.alabar.org/for-the-public/find-a-lawyer/",
# #         "instructions": "Enter the attorney's name or bar number in the search field"
# #     },
# #     "AK": {
# #         "name": "Alaska Bar Association",
# #         "url": "https://alaskabar.org/for-the-public/lawyer-directory/",
# #         "instructions": "Search by attorney name in the directory"
# #     },
# #     "AZ": {
# #         "name": "State Bar of Arizona",
# #         "url": "https://www.azbar.org/for-the-public/find-a-lawyer/",
# #         "instructions": "Use the lawyer finder tool with name or bar number"
# #     },
# #     "AR": {
# #         "name": "Arkansas Bar Association",
# #         "url": "https://www.arcourts.gov/professional-and-lawyer-regulation/attorney-search",
# #         "instructions": "Search the attorney database"
# #     },
# #     "CA": {
# #         "name": "State Bar of California",
# #         "url": "https://apps.calbar.ca.gov/attorney/Licensee/Detail/",
# #         "instructions": "Add the bar number to the end of the URL, or search at calbar.ca.gov",
# #         "direct_link": True
# #     },
# #     "CO": {
# #         "name": "Colorado Supreme Court",
# #         "url": "https://www.coloradosupremecourt.com/Search/AttSearch.asp",
# #         "instructions": "Enter attorney name or registration number"
# #     },
# #     "CT": {
# #         "name": "Connecticut Bar",
# #         "url": "https://www.jud.ct.gov/attorneyfirminquiry/",
# #         "instructions": "Search by attorney name or juris number"
# #     },
# #     "DE": {
# #         "name": "Delaware Courts",
# #         "url": "https://courts.delaware.gov/odc/attorneysearch.aspx",
# #         "instructions": "Search by name or bar ID"
# #     },
# #     "DC": {
# #         "name": "District of Columbia Bar",
# #         "url": "https://www.dcbar.org/for-the-public/find-a-lawyer",
# #         "instructions": "Use the lawyer directory search"
# #     },
# #     "FL": {
# #         "name": "The Florida Bar",
# #         "url": "https://www.floridabar.org/directories/find-mbr/",
# #         "instructions": "Search by name or bar number"
# #     },
# #     "GA": {
# #         "name": "State Bar of Georgia",
# #         "url": "https://www.gabar.org/membersearchresults.cfm",
# #         "instructions": "Enter search criteria to find the attorney"
# #     },
# #     "HI": {
# #         "name": "Hawaii State Bar Association",
# #         "url": "https://hsba.org/HSBA/For_the_Public/HSBA/Public/find-a-lawyer.aspx",
# #         "instructions": "Search the lawyer directory"
# #     },
# #     "ID": {
# #         "name": "Idaho State Bar",
# #         "url": "https://isb.idaho.gov/licensing/attorney-licensing/attorney-roster/",
# #         "instructions": "Search the attorney roster"
# #     },
# #     "IL": {
# #         "name": "Illinois ARDC",
# #         "url": "https://www.iardc.org/ldetail.asp",
# #         "instructions": "Enter the ARDC registration number"
# #     },
# #     "IN": {
# #         "name": "Indiana Roll of Attorneys",
# #         "url": "https://www.in.gov/courts/iocs/admin/radp/",
# #         "instructions": "Search the Roll of Attorneys database"
# #     },
# #     "IA": {
# #         "name": "Iowa State Bar Association",
# #         "url": "https://www.iowabar.org/page/FindALawyer",
# #         "instructions": "Use the Find a Lawyer feature"
# #     },
# #     "KS": {
# #         "name": "Kansas Bar Association",
# #         "url": "https://www.ksbar.org/page/findlawyer",
# #         "instructions": "Search the attorney directory"
# #     },
# #     "KY": {
# #         "name": "Kentucky Bar Association",
# #         "url": "https://www.kybar.org/search/custom.asp?id=2818",
# #         "instructions": "Search by name or bar number"
# #     },
# #     "LA": {
# #         "name": "Louisiana State Bar Association",
# #         "url": "https://www.lsba.org/Public/FindLegalHelp.aspx",
# #         "instructions": "Use the lawyer lookup tool"
# #     },
# #     "ME": {
# #         "name": "Maine Board of Bar Overseers",
# #         "url": "https://www.mebaroverseers.org/attorney_registration/searchlawyerinquiry.asp",
# #         "instructions": "Search the lawyer inquiry database"
# #     },
# #     "MD": {
# #         "name": "Maryland Courts",
# #         "url": "https://www.courts.state.md.us/lawyers/attylist",
# #         "instructions": "Search the attorney directory"
# #     },
# #     "MA": {
# #         "name": "Massachusetts Board of Bar Overseers",
# #         "url": "https://www.massbbo.org/Lookup",
# #         "instructions": "Enter attorney name or BBO number"
# #     },
# #     "MI": {
# #         "name": "State Bar of Michigan",
# #         "url": "https://www.zeekbeek.com/SBM",
# #         "instructions": "Search for attorneys by name"
# #     },
# #     "MN": {
# #         "name": "Minnesota Lawyer Registration",
# #         "url": "https://lro.mncourts.gov/Directory/Search",
# #         "instructions": "Search by name or ID number"
# #     },
# #     "MS": {
# #         "name": "Mississippi Bar",
# #         "url": "https://www.msbar.org/for-the-public/find-an-attorney/",
# #         "instructions": "Use the attorney search"
# #     },
# #     "MO": {
# #         "name": "Missouri Bar",
# #         "url": "https://mobar.org/site/content/Find-a-Lawyer.aspx",
# #         "instructions": "Search the lawyer directory"
# #     },
# #     "MT": {
# #         "name": "State Bar of Montana",
# #         "url": "https://www.montanabar.org/page/LawyerSearch",
# #         "instructions": "Search for attorneys"
# #     },
# #     "NE": {
# #         "name": "Nebraska State Bar",
# #         "url": "https://www.nebar.com/search/custom.asp?id=2040",
# #         "instructions": "Search the attorney directory"
# #     },
# #     "NV": {
# #         "name": "State Bar of Nevada",
# #         "url": "https://www.nvbar.org/find-a-lawyer/",
# #         "instructions": "Use the attorney search"
# #     },
# #     "NH": {
# #         "name": "New Hampshire Bar Association",
# #         "url": "https://www.nhbar.org/lawyer-referral-service/find-a-lawyer",
# #         "instructions": "Search for attorneys"
# #     },
# #     "NJ": {
# #         "name": "New Jersey Courts",
# #         "url": "https://portal.njcourts.gov/njattywebpub/attorneySearch.action",
# #         "instructions": "Search by name or attorney ID"
# #     },
# #     "NM": {
# #         "name": "State Bar of New Mexico",
# #         "url": "https://www.sbnm.org/For-Public/Find-an-Attorney",
# #         "instructions": "Search the attorney directory"
# #     },
# #     "NY": {
# #         "name": "New York Courts Attorney Search",
# #         "url": "https://iapps.courts.state.ny.us/attorneyservices/search",
# #         "instructions": "Search by name or registration number"
# #     },
# #     "NC": {
# #         "name": "North Carolina State Bar",
# #         "url": "https://www.ncbar.gov/for-the-public/find-a-lawyer/",
# #         "instructions": "Search the lawyer directory"
# #     },
# #     "ND": {
# #         "name": "State Bar Association of North Dakota",
# #         "url": "https://www.sband.org/page/findattorney",
# #         "instructions": "Search for attorneys"
# #     },
# #     "OH": {
# #         "name": "Ohio State Bar Association",
# #         "url": "https://www.supremecourt.ohio.gov/Attorney/Search/",
# #         "instructions": "Search by name or registration number"
# #     },
# #     "OK": {
# #         "name": "Oklahoma Bar Association",
# #         "url": "https://www.okbar.org/findalawyer/",
# #         "instructions": "Use the lawyer search tool"
# #     },
# #     "OR": {
# #         "name": "Oregon State Bar",
# #         "url": "https://www.osbar.org/members/search.asp",
# #         "instructions": "Search by name or bar number"
# #     },
# #     "PA": {
# #         "name": "Pennsylvania Disciplinary Board",
# #         "url": "https://www.padisciplinaryboard.org/for-the-public/find-attorney",
# #         "instructions": "Search for attorneys by name"
# #     },
# #     "RI": {
# #         "name": "Rhode Island Bar Association",
# #         "url": "https://www.ribar.com/for-the-public/find-a-lawyer/",
# #         "instructions": "Use the lawyer finder"
# #     },
# #     "SC": {
# #         "name": "South Carolina Bar",
# #         "url": "https://www.scbar.org/public/find-a-lawyer/",
# #         "instructions": "Search the attorney directory"
# #     },
# #     "SD": {
# #         "name": "State Bar of South Dakota",
# #         "url": "https://www.statebarofsouthdakota.com/page/findanattorney",
# #         "instructions": "Search for attorneys"
# #     },
# #     "TN": {
# #         "name": "Tennessee Board of Professional Responsibility",
# #         "url": "https://www.tbpr.org/attorneys/find-an-attorney",
# #         "instructions": "Search by name or BPR number"
# #     },
# #     "TX": {
# #         "name": "State Bar of Texas",
# #         "url": "https://www.texasbar.com/AM/Template.cfm?Section=Find_A_Lawyer",
# #         "instructions": "Search by name or bar number"
# #     },
# #     "UT": {
# #         "name": "Utah State Bar",
# #         "url": "https://www.utahbar.org/public-services/find-a-lawyer/",
# #         "instructions": "Use the lawyer finder"
# #     },
# #     "VT": {
# #         "name": "Vermont Bar Association",
# #         "url": "https://www.vtbar.org/for-the-public/find-a-lawyer/",
# #         "instructions": "Search for attorneys"
# #     },
# #     "VA": {
# #         "name": "Virginia State Bar",
# #         "url": "https://www.vsb.org/vlrs/",
# #         "instructions": "Use the lawyer referral service"
# #     },
# #     "WA": {
# #         "name": "Washington State Bar Association",
# #         "url": "https://www.wsba.org/for-the-public/find-legal-help",
# #         "instructions": "Search the lawyer directory"
# #     },
# #     "WV": {
# #         "name": "West Virginia State Bar",
# #         "url": "https://www.wvbar.org/for-the-public/find-a-lawyer/",
# #         "instructions": "Search for attorneys"
# #     },
# #     "WI": {
# #         "name": "State Bar of Wisconsin",
# #         "url": "https://www.wisbar.org/forpublic/pages/find-a-lawyer.aspx",
# #         "instructions": "Use the lawyer search"
# #     },
# #     "WY": {
# #         "name": "Wyoming State Bar",
# #         "url": "https://www.wyomingbar.org/for-the-public/find-a-lawyer/",
# #         "instructions": "Search the attorney directory"
# #     }
# # }

# # # CourtListener jurisdiction mappings
# # COURTLISTENER_JURISDICTIONS = {
# #     "ca": "calctapp,cal",
# #     "tx": "tex,texcrimapp,texapp",
# #     "ny": "ny,nyappdiv,nysupct",
# #     "fl": "fla,fladistctapp",
# #     "il": "ill,illappct",
# #     "pa": "pa,pasuperct",
# #     "oh": "ohio,ohioctapp",
# #     "ga": "ga,gactapp",
# #     "nc": "nc,ncctapp",
# #     "nj": "nj,njsuperctappdiv",
# #     "mi": "mich,michctapp",
# #     "va": "va,vactapp",
# #     "wa": "wash,washctapp",
# #     "az": "ariz,arizctapp",
# #     "ma": "mass,massappct",
# #     "in": "ind,indctapp",
# #     "tn": "tenn,tennctapp",
# #     "mo": "mo,moctapp",
# #     "md": "md,mdctspecapp",
# #     "wi": "wis,wisctapp",
# #     "co": "colo,coloctapp",
# #     "mn": "minn,minnctapp",
# #     "al": "ala,alactapp",
# #     "sc": "sc,scctapp",
# #     "la": "la,lactapp",
# #     "ky": "ky,kyctapp",
# #     "or": "or,orctapp",
# #     "ok": "okla,oklacivapp,oklacrimapp",
# #     "ct": "conn,connappct",
# #     "ia": "iowa,iowactapp",
# #     "ms": "miss,missctapp",
# #     "ar": "ark,arkctapp",
# #     "ks": "kan,kanctapp",
# #     "ut": "utah,utahctapp",
# #     "nv": "nev,nevapp",
# #     "nm": "nm,nmctapp",
# #     "ne": "neb,nebctapp",
# #     "wv": "wva",
# #     "id": "idaho,idahoctapp",
# #     "hi": "haw,hawapp",
# #     "me": "me",
# #     "nh": "nh",
# #     "ri": "ri",
# #     "mt": "mont",
# #     "de": "del,delch,delsuperct",
# #     "sd": "sd",
# #     "nd": "nd,ndctapp",
# #     "ak": "alaska,alaskactapp",
# #     "dc": "dc,dcctapp",
# #     "vt": "vt",
# #     "wy": "wyo",
# #     "scotus": "scotus",
# #     "federal": "ca1,ca2,ca3,ca4,ca5,ca6,ca7,ca8,ca9,ca10,ca11,cadc,cafc"
# # }

# # # ============================================================================
# # # HELPER FUNCTIONS
# # # ============================================================================

# # def get_timestamp() -> str:
# #     """Get current UTC timestamp in ISO format"""
# #     return datetime.utcnow().isoformat() + "Z"

# # def get_state_bar_info(state: str) -> Dict[str, str]:
# #     """Get state bar information for a given state code"""
# #     state = state.upper()
# #     if state in STATE_BAR_INFO:
# #         return STATE_BAR_INFO[state]
# #     return {
# #         "name": f"{state} State Bar",
# #         "url": "https://www.americanbar.org/groups/legal_services/flh-home/",
# #         "instructions": "Visit the American Bar Association to find your state bar"
# #     }

# # def build_verification_url(state: str, bar_number: str) -> str:
# #     """Build the verification URL for a state, with direct linking if available"""
# #     state = state.upper()
# #     info = STATE_BAR_INFO.get(state, {})
    
# #     # California supports direct linking
# #     if state == "CA" and bar_number:
# #         return f"https://apps.calbar.ca.gov/attorney/Licensee/Detail/{bar_number}"
    
# #     # Return base URL for other states
# #     return info.get("url", "https://www.americanbar.org/groups/legal_services/flh-home/")

# # # ============================================================================
# # # COURTLISTENER API INTEGRATION
# # # ============================================================================

# # async def search_courtlistener(
# #     query: str,
# #     jurisdiction: Optional[str] = None,
# #     date_after: Optional[str] = None,
# #     limit: int = 5
# # ) -> CaseSearchResponse:
# #     """
# #     Search CourtListener for case law
    
# #     CourtListener API Docs: https://www.courtlistener.com/help/api/rest/
# #     """
    
# #     base_url = "https://www.courtlistener.com/api/rest/v4/search/"
    
# #     # Build search parameters
# #     params = {
# #         "q": query,
# #         "type": "o",  # Search opinions
# #         "order_by": "score desc",
# #         "page_size": min(limit, 20)
# #     }
    
# #     # Add jurisdiction filter if provided
# #     if jurisdiction:
# #         jurisdiction = jurisdiction.lower()
# #         if jurisdiction in COURTLISTENER_JURISDICTIONS:
# #             params["court"] = COURTLISTENER_JURISDICTIONS[jurisdiction]
# #         else:
# #             params["court"] = jurisdiction
    
# #     # Add date filter if provided
# #     if date_after:
# #         params["filed_after"] = date_after
    
# #     # Build headers
# #     headers = {
# #         "User-Agent": "LegalNav-API/1.0 (IBM-DevDay-Hackathon)"
# #     }
# #     if COURTLISTENER_API_TOKEN:
# #         headers["Authorization"] = f"Token {COURTLISTENER_API_TOKEN}"
    
# #     logger.info(f"Searching CourtListener: query='{query}', jurisdiction='{jurisdiction}', limit={limit}")
    
# #     async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
# #         try:
# #             response = await client.get(base_url, params=params, headers=headers)
# #             response.raise_for_status()
# #             data = response.json()
            
# #             cases = []
# #             for result in data.get("results", [])[:limit]:
# #                 # Extract citation (can be a list)
# #                 citations = result.get("citation", [])
# #                 citation = None
# #                 if isinstance(citations, list) and citations:
# #                     citation = citations[0]
# #                 elif isinstance(citations, str):
# #                     citation = citations
                
# #                 # Extract snippet/summary
# #                 snippet = result.get("snippet", "")
# #                 if snippet:
# #                     # Clean up HTML tags from snippet
# #                     snippet = snippet.replace("<mark>", "**").replace("</mark>", "**")
# #                     snippet = snippet[:500] + "..." if len(snippet) > 500 else snippet
                
# #                 # Build absolute URL
# #                 absolute_url = result.get("absolute_url", "")
# #                 if absolute_url and not absolute_url.startswith("http"):
# #                     absolute_url = f"https://www.courtlistener.com{absolute_url}"
# #                 elif not absolute_url:
# #                     cluster_id = result.get("cluster_id", "")
# #                     if cluster_id:
# #                         absolute_url = f"https://www.courtlistener.com/opinion/{cluster_id}/"
                
# #                 cases.append(CaseResult(
# #                     case_name=result.get("caseName", result.get("case_name", "Unknown Case")),
# #                     citation=citation,
# #                     date_filed=result.get("dateFiled", result.get("date_filed", "Unknown")),
# #                     court=result.get("court", result.get("court_id", "Unknown Court")),
# #                     court_id=result.get("court_id"),
# #                     summary=snippet if snippet else None,
# #                     url=absolute_url if absolute_url else "https://www.courtlistener.com"
# #                 ))
            
# #             logger.info(f"Found {len(cases)} cases out of {data.get('count', 0)} total")
            
# #             return CaseSearchResponse(
# #                 success=True,
# #                 cases=cases,
# #                 total_results=data.get("count", 0),
# #                 query_used=query,
# #                 source="CourtListener (Free Law Project)",
# #                 source_url="https://www.courtlistener.com",
# #                 retrieved_at=get_timestamp()
# #             )
            
# #         except httpx.HTTPStatusError as e:
# #             logger.error(f"CourtListener HTTP error: {e.response.status_code} - {e.response.text}")
# #             raise HTTPException(
# #                 status_code=e.response.status_code,
# #                 detail=f"CourtListener API error: {e.response.text}"
# #             )
# #         except httpx.TimeoutException:
# #             logger.error("CourtListener request timed out")
# #             raise HTTPException(
# #                 status_code=504,
# #                 detail="Search request timed out. Please try again with a simpler query."
# #             )
# #         except Exception as e:
# #             logger.error(f"CourtListener search failed: {str(e)}")
# #             raise HTTPException(
# #                 status_code=500,
# #                 detail=f"Search failed: {str(e)}"
# #             )

# # # ============================================================================
# # # API ENDPOINTS
# # # ============================================================================

# # @app.get("/", response_model=Dict[str, Any])
# # async def root():
# #     """
# #     Root endpoint - API information and health check
    
# #     Returns basic information about the LegalNav API including
# #     available endpoints and service status.
# #     """
# #     return {
# #         "service": "LegalNav Live API",
# #         "version": "1.0.0",
# #         "status": "running",
# #         "hackathon": "IBM Dev Day: AI Demystified 2026",
# #         "description": "Real-time legal data API for watsonx Orchestrate",
# #         "endpoints": {
# #             "documentation": "/docs",
# #             "health": "/api/v1/health",
# #             "search_cases": "/api/v1/cases/search",
# #             "verify_attorney": "/api/v1/attorneys/verify"
# #         },
# #         "data_sources": {
# #             "case_law": "CourtListener (Free Law Project)",
# #             "attorney_verification": "State Bar Associations"
# #         },
# #         "timestamp": get_timestamp()
# #     }

# # @app.get("/api/v1/health", response_model=HealthResponse)
# # async def health_check():
# #     """
# #     Health check endpoint
    
# #     Returns the current status of the API including whether
# #     external service credentials are configured.
# #     """
# #     return HealthResponse(
# #         status="healthy",
# #         service="LegalNav Live API",
# #         version="1.0.0",
# #         timestamp=get_timestamp(),
# #         courtlistener_configured=bool(COURTLISTENER_API_TOKEN)
# #     )

# # @app.post(
# #     "/api/v1/cases/search",
# #     response_model=CaseSearchResponse,
# #     responses={
# #         400: {"model": ErrorResponse, "description": "Invalid request parameters"},
# #         500: {"model": ErrorResponse, "description": "Server error"},
# #         504: {"model": ErrorResponse, "description": "Request timeout"}
# #     }
# # )
# # async def search_cases(request: CaseSearchRequest):
# #     """
# #     Search CourtListener for relevant case law and legal precedents.
    
# #     This endpoint searches the CourtListener database (Free Law Project),
# #     which contains over 8 million court opinions from federal and state courts.
    
# #     **Use Cases:**
# #     - Find cases related to tenant rights, evictions, habitability
# #     - Research employment law precedents
# #     - Find family law cases about custody, support
# #     - Search for civil rights cases
# #     - Research consumer protection cases
    
# #     **Tips for Better Results:**
# #     - Use specific legal terms (e.g., "implied warranty habitability" not "apartment problems")
# #     - Add jurisdiction for state-specific results
# #     - Use date filters for recent precedents
    
# #     **Example Queries:**
# #     - "tenant eviction retaliatory habitability"
# #     - "wrongful termination whistleblower at-will employment"
# #     - "custody modification best interest child"
# #     - "wage theft unpaid overtime FLSA"
# #     """
# #     return await search_courtlistener(
# #         query=request.query,
# #         jurisdiction=request.jurisdiction,
# #         date_after=request.date_after,
# #         limit=request.limit
# #     )

# # @app.post(
# #     "/api/v1/attorneys/verify",
# #     response_model=VerifyAttorneyResponse,
# #     responses={
# #         400: {"model": ErrorResponse, "description": "Invalid state code or bar number"}
# #     }
# # )
# # async def verify_attorney(request: VerifyAttorneyRequest):
# #     """
# #     Get verification information for an attorney's bar status.
    
# #     Returns the official state bar verification URL where users can
# #     confirm an attorney's current license status and standing.
    
# #     **What This Returns:**
# #     - Direct link to official state bar verification page
# #     - Instructions on how to verify
# #     - State bar contact information
    
# #     **Supported for All 50 States + DC**
    
# #     **Note:** For privacy and accuracy, users should verify directly
# #     with the state bar using the provided URL rather than relying
# #     on cached or third-party data.
# #     """
# #     state = request.state.upper()
# #     bar_number = request.bar_number.strip()
    
# #     # Validate state code
# #     if state not in STATE_BAR_INFO:
# #         raise HTTPException(
# #             status_code=400,
# #             detail=f"Invalid state code: {state}. Use two-letter state codes (e.g., CA, TX, NY)."
# #         )
    
# #     info = STATE_BAR_INFO[state]
# #     verification_url = build_verification_url(state, bar_number)
    
# #     logger.info(f"Attorney verification request: state={state}, bar_number={bar_number}")
    
# #     return VerifyAttorneyResponse(
# #         success=True,
# #         verified=None,  # Manual verification required
# #         status="Verification URL provided - please check directly with state bar",
# #         name=None,
# #         admission_date=None,
# #         discipline_history=False,
# #         verification_url=verification_url,
# #         state_bar_name=info["name"],
# #         instructions=info["instructions"],
# #         retrieved_at=get_timestamp()
# #     )

# # # ============================================================================
# # # ADDITIONAL ENDPOINTS FOR WATSONX ORCHESTRATE
# # # ============================================================================

# # @app.get(
# #     "/api/v1/jurisdictions",
# #     response_model=Dict[str, Any]
# # )
# # async def list_jurisdictions():
# #     """
# #     List available court jurisdictions for case search.
    
# #     Returns a mapping of jurisdiction codes that can be used
# #     with the case search endpoint.
# #     """
# #     return {
# #         "jurisdictions": {
# #             code: {"courts": courts}
# #             for code, courts in COURTLISTENER_JURISDICTIONS.items()
# #         },
# #         "common": {
# #             "scotus": "United States Supreme Court",
# #             "federal": "All Federal Circuit Courts",
# #             "ca": "California State Courts",
# #             "tx": "Texas State Courts",
# #             "ny": "New York State Courts",
# #             "fl": "Florida State Courts"
# #         },
# #         "note": "Use lowercase jurisdiction codes in the search request"
# #     }

# # @app.get(
# #     "/api/v1/states",
# #     response_model=Dict[str, Any]
# # )
# # async def list_states():
# #     """
# #     List all supported states for attorney verification.
    
# #     Returns information about all 50 states + DC including
# #     their state bar names and verification URLs.
# #     """
# #     return {
# #         "states": {
# #             code: {
# #                 "name": info["name"],
# #                 "verification_url": info["url"]
# #             }
# #             for code, info in STATE_BAR_INFO.items()
# #         },
# #         "total": len(STATE_BAR_INFO),
# #         "note": "Use uppercase state codes (e.g., CA, TX, NY)"
# #     }

# # # ============================================================================
# # # ERROR HANDLERS
# # # ============================================================================

# # @app.exception_handler(HTTPException)
# # async def http_exception_handler(request, exc):
# #     """Handle HTTP exceptions with consistent format"""
# #     return JSONResponse(
# #         status_code=exc.status_code,
# #         content={
# #             "success": False,
# #             "error": exc.detail,
# #             "error_code": f"HTTP_{exc.status_code}",
# #             "timestamp": get_timestamp()
# #         }
# #     )

# # @app.exception_handler(Exception)
# # async def general_exception_handler(request, exc):
# #     """Handle unexpected exceptions"""
# #     logger.error(f"Unexpected error: {str(exc)}")
# #     return JSONResponse(
# #         status_code=500,
# #         content={
# #             "success": False,
# #             "error": "An unexpected error occurred",
# #             "error_code": "INTERNAL_ERROR",
# #             "timestamp": get_timestamp()
# #         }
# #     )

# # # ============================================================================
# # # MAIN ENTRY POINT
# # # ============================================================================

# # if __name__ == "__main__":
# #     import uvicorn
# #     port = int(os.getenv("PORT", 8000))
# #     uvicorn.run(
# #         "main:app",
# #         host="0.0.0.0",
# #         port=port,
# #         reload=os.getenv("ENVIRONMENT", "production") == "development"
# #     )
