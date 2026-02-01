"""
LegalNav Live API
=================
Real-time legal data integration for IBM watsonx Orchestrate
IBM Dev Day: AI Demystified Hackathon 2026

This API provides:
1. Case Law Search via CourtListener (Free Law Project)
2. Attorney Bar Status Verification URLs

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

### 🏛️ Built for IBM Dev Day: AI Demystified Hackathon 2026

**Data Sources:**
- CourtListener API (Free Law Project) - 8+ million court opinions
- State Bar Association websites - All 50 states + DC

**Note:** This API provides legal information, not legal advice.
    """,
    version="1.0.0",
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
# Get your free token at: https://www.courtlistener.com/help/api/rest/
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
    location: Optional[str] = Field(
        None,
        min_length=2,
        max_length=50,
        description="State or location to focus the search (e.g., 'California', 'New York', 'Texas'). This will be added to the search query to find relevant cases from that location.",
        examples=["California", "New York", "Texas", "Florida"]
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

    class Config:
        json_schema_extra = {
            "example": {
                "query": "tenant eviction habitability",
                "location": "California",
                "date_after": "2020-01-01",
                "limit": 5
            }
        }

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

    class Config:
        json_schema_extra = {
            "example": {
                "state": "CA",
                "bar_number": "123456"
            }
        }

# ============================================================================
# PYDANTIC MODELS - RESPONSE
# ============================================================================

class CaseResult(BaseModel):
    """Individual case result from search"""
    case_name: str = Field(..., description="Full case name (e.g., 'Smith v. Jones')")
    citation: Optional[str] = Field(None, description="Official legal citation if available")
    date_filed: str = Field(..., description="Date the case was filed or decided")
    court: str = Field(..., description="Name of the court")
    court_id: Optional[str] = Field(None, description="CourtListener court identifier")
    summary: Optional[str] = Field(None, description="Brief excerpt from the opinion")
    url: str = Field(..., description="Link to read the full opinion on CourtListener")

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

class VerifyAttorneyResponse(BaseModel):
    """Response model for attorney verification"""
    success: bool = Field(True, description="Whether the lookup was successful")
    verified: Optional[bool] = Field(
        None, 
        description="True if verified active, False if inactive/suspended, null if manual check required"
    )
    status: str = Field(..., description="Current bar status or instruction")
    name: Optional[str] = Field(None, description="Attorney's registered name if available")
    admission_date: Optional[str] = Field(None, description="Bar admission date if available")
    discipline_history: bool = Field(False, description="Whether disciplinary records exist")
    verification_url: str = Field(..., description="Official state bar verification URL")
    state_bar_name: str = Field(..., description="Name of the state bar association")
    instructions: str = Field(..., description="How to use the verification URL")
    retrieved_at: str = Field(..., description="ISO timestamp")

class HealthResponse(BaseModel):
    """Health check response"""
    status: str = Field("healthy", description="API health status")
    service: str = Field("LegalNav Live API", description="Service name")
    version: str = Field("1.0.0", description="API version")
    timestamp: str = Field(..., description="Current server time")
    courtlistener_configured: bool = Field(..., description="Whether CourtListener token is set")

class ErrorResponse(BaseModel):
    """Error response model"""
    success: bool = Field(False)
    error: str = Field(..., description="Error message")
    error_code: str = Field(..., description="Error code for debugging")
    timestamp: str = Field(..., description="When the error occurred")

# ============================================================================
# STATE BAR VERIFICATION URLS - COMPREHENSIVE LIST
# ============================================================================

STATE_BAR_INFO: Dict[str, Dict[str, str]] = {
    "AL": {
        "name": "Alabama State Bar",
        "url": "https://www.alabar.org/for-the-public/find-a-lawyer/",
        "instructions": "Enter the attorney's name or bar number in the search field"
    },
    "AK": {
        "name": "Alaska Bar Association",
        "url": "https://alaskabar.org/for-the-public/lawyer-directory/",
        "instructions": "Search by attorney name in the directory"
    },
    "AZ": {
        "name": "State Bar of Arizona",
        "url": "https://www.azbar.org/for-the-public/find-a-lawyer/",
        "instructions": "Use the lawyer finder tool with name or bar number"
    },
    "AR": {
        "name": "Arkansas Bar Association",
        "url": "https://www.arcourts.gov/professional-and-lawyer-regulation/attorney-search",
        "instructions": "Search the attorney database"
    },
    "CA": {
        "name": "State Bar of California",
        "url": "https://apps.calbar.ca.gov/attorney/Licensee/Detail/",
        "instructions": "Add the bar number to the end of the URL, or search at calbar.ca.gov",
        "direct_link": True
    },
    "CO": {
        "name": "Colorado Supreme Court",
        "url": "https://www.coloradosupremecourt.com/Search/AttSearch.asp",
        "instructions": "Enter attorney name or registration number"
    },
    "CT": {
        "name": "Connecticut Bar",
        "url": "https://www.jud.ct.gov/attorneyfirminquiry/",
        "instructions": "Search by attorney name or juris number"
    },
    "DE": {
        "name": "Delaware Courts",
        "url": "https://courts.delaware.gov/odc/attorneysearch.aspx",
        "instructions": "Search by name or bar ID"
    },
    "DC": {
        "name": "District of Columbia Bar",
        "url": "https://www.dcbar.org/for-the-public/find-a-lawyer",
        "instructions": "Use the lawyer directory search"
    },
    "FL": {
        "name": "The Florida Bar",
        "url": "https://www.floridabar.org/directories/find-mbr/",
        "instructions": "Search by name or bar number"
    },
    "GA": {
        "name": "State Bar of Georgia",
        "url": "https://www.gabar.org/membersearchresults.cfm",
        "instructions": "Enter search criteria to find the attorney"
    },
    "HI": {
        "name": "Hawaii State Bar Association",
        "url": "https://hsba.org/HSBA/For_the_Public/HSBA/Public/find-a-lawyer.aspx",
        "instructions": "Search the lawyer directory"
    },
    "ID": {
        "name": "Idaho State Bar",
        "url": "https://isb.idaho.gov/licensing/attorney-licensing/attorney-roster/",
        "instructions": "Search the attorney roster"
    },
    "IL": {
        "name": "Illinois ARDC",
        "url": "https://www.iardc.org/ldetail.asp",
        "instructions": "Enter the ARDC registration number"
    },
    "IN": {
        "name": "Indiana Roll of Attorneys",
        "url": "https://www.in.gov/courts/iocs/admin/radp/",
        "instructions": "Search the Roll of Attorneys database"
    },
    "IA": {
        "name": "Iowa State Bar Association",
        "url": "https://www.iowabar.org/page/FindALawyer",
        "instructions": "Use the Find a Lawyer feature"
    },
    "KS": {
        "name": "Kansas Bar Association",
        "url": "https://www.ksbar.org/page/findlawyer",
        "instructions": "Search the attorney directory"
    },
    "KY": {
        "name": "Kentucky Bar Association",
        "url": "https://www.kybar.org/search/custom.asp?id=2818",
        "instructions": "Search by name or bar number"
    },
    "LA": {
        "name": "Louisiana State Bar Association",
        "url": "https://www.lsba.org/Public/FindLegalHelp.aspx",
        "instructions": "Use the lawyer lookup tool"
    },
    "ME": {
        "name": "Maine Board of Bar Overseers",
        "url": "https://www.mebaroverseers.org/attorney_registration/searchlawyerinquiry.asp",
        "instructions": "Search the lawyer inquiry database"
    },
    "MD": {
        "name": "Maryland Courts",
        "url": "https://www.courts.state.md.us/lawyers/attylist",
        "instructions": "Search the attorney directory"
    },
    "MA": {
        "name": "Massachusetts Board of Bar Overseers",
        "url": "https://www.massbbo.org/Lookup",
        "instructions": "Enter attorney name or BBO number"
    },
    "MI": {
        "name": "State Bar of Michigan",
        "url": "https://www.zeekbeek.com/SBM",
        "instructions": "Search for attorneys by name"
    },
    "MN": {
        "name": "Minnesota Lawyer Registration",
        "url": "https://lro.mncourts.gov/Directory/Search",
        "instructions": "Search by name or ID number"
    },
    "MS": {
        "name": "Mississippi Bar",
        "url": "https://www.msbar.org/for-the-public/find-an-attorney/",
        "instructions": "Use the attorney search"
    },
    "MO": {
        "name": "Missouri Bar",
        "url": "https://mobar.org/site/content/Find-a-Lawyer.aspx",
        "instructions": "Search the lawyer directory"
    },
    "MT": {
        "name": "State Bar of Montana",
        "url": "https://www.montanabar.org/page/LawyerSearch",
        "instructions": "Search for attorneys"
    },
    "NE": {
        "name": "Nebraska State Bar",
        "url": "https://www.nebar.com/search/custom.asp?id=2040",
        "instructions": "Search the attorney directory"
    },
    "NV": {
        "name": "State Bar of Nevada",
        "url": "https://www.nvbar.org/find-a-lawyer/",
        "instructions": "Use the attorney search"
    },
    "NH": {
        "name": "New Hampshire Bar Association",
        "url": "https://www.nhbar.org/lawyer-referral-service/find-a-lawyer",
        "instructions": "Search for attorneys"
    },
    "NJ": {
        "name": "New Jersey Courts",
        "url": "https://portal.njcourts.gov/njattywebpub/attorneySearch.action",
        "instructions": "Search by name or attorney ID"
    },
    "NM": {
        "name": "State Bar of New Mexico",
        "url": "https://www.sbnm.org/For-Public/Find-an-Attorney",
        "instructions": "Search the attorney directory"
    },
    "NY": {
        "name": "New York Courts Attorney Search",
        "url": "https://iapps.courts.state.ny.us/attorneyservices/search",
        "instructions": "Search by name or registration number"
    },
    "NC": {
        "name": "North Carolina State Bar",
        "url": "https://www.ncbar.gov/for-the-public/find-a-lawyer/",
        "instructions": "Search the lawyer directory"
    },
    "ND": {
        "name": "State Bar Association of North Dakota",
        "url": "https://www.sband.org/page/findattorney",
        "instructions": "Search for attorneys"
    },
    "OH": {
        "name": "Ohio State Bar Association",
        "url": "https://www.supremecourt.ohio.gov/Attorney/Search/",
        "instructions": "Search by name or registration number"
    },
    "OK": {
        "name": "Oklahoma Bar Association",
        "url": "https://www.okbar.org/findalawyer/",
        "instructions": "Use the lawyer search tool"
    },
    "OR": {
        "name": "Oregon State Bar",
        "url": "https://www.osbar.org/members/search.asp",
        "instructions": "Search by name or bar number"
    },
    "PA": {
        "name": "Pennsylvania Disciplinary Board",
        "url": "https://www.padisciplinaryboard.org/for-the-public/find-attorney",
        "instructions": "Search for attorneys by name"
    },
    "RI": {
        "name": "Rhode Island Bar Association",
        "url": "https://www.ribar.com/for-the-public/find-a-lawyer/",
        "instructions": "Use the lawyer finder"
    },
    "SC": {
        "name": "South Carolina Bar",
        "url": "https://www.scbar.org/public/find-a-lawyer/",
        "instructions": "Search the attorney directory"
    },
    "SD": {
        "name": "State Bar of South Dakota",
        "url": "https://www.statebarofsouthdakota.com/page/findanattorney",
        "instructions": "Search for attorneys"
    },
    "TN": {
        "name": "Tennessee Board of Professional Responsibility",
        "url": "https://www.tbpr.org/attorneys/find-an-attorney",
        "instructions": "Search by name or BPR number"
    },
    "TX": {
        "name": "State Bar of Texas",
        "url": "https://www.texasbar.com/AM/Template.cfm?Section=Find_A_Lawyer",
        "instructions": "Search by name or bar number"
    },
    "UT": {
        "name": "Utah State Bar",
        "url": "https://www.utahbar.org/public-services/find-a-lawyer/",
        "instructions": "Use the lawyer finder"
    },
    "VT": {
        "name": "Vermont Bar Association",
        "url": "https://www.vtbar.org/for-the-public/find-a-lawyer/",
        "instructions": "Search for attorneys"
    },
    "VA": {
        "name": "Virginia State Bar",
        "url": "https://www.vsb.org/vlrs/",
        "instructions": "Use the lawyer referral service"
    },
    "WA": {
        "name": "Washington State Bar Association",
        "url": "https://www.wsba.org/for-the-public/find-legal-help",
        "instructions": "Search the lawyer directory"
    },
    "WV": {
        "name": "West Virginia State Bar",
        "url": "https://www.wvbar.org/for-the-public/find-a-lawyer/",
        "instructions": "Search for attorneys"
    },
    "WI": {
        "name": "State Bar of Wisconsin",
        "url": "https://www.wisbar.org/forpublic/pages/find-a-lawyer.aspx",
        "instructions": "Use the lawyer search"
    },
    "WY": {
        "name": "Wyoming State Bar",
        "url": "https://www.wyomingbar.org/for-the-public/find-a-lawyer/",
        "instructions": "Search the attorney directory"
    }
}

# CourtListener jurisdiction mappings
COURTLISTENER_JURISDICTIONS = {
    "ca": "calctapp,cal",
    "tx": "tex,texcrimapp,texapp",
    "ny": "ny,nyappdiv,nysupct",
    "fl": "fla,fladistctapp",
    "il": "ill,illappct",
    "pa": "pa,pasuperct",
    "oh": "ohio,ohioctapp",
    "ga": "ga,gactapp",
    "nc": "nc,ncctapp",
    "nj": "nj,njsuperctappdiv",
    "mi": "mich,michctapp",
    "va": "va,vactapp",
    "wa": "wash,washctapp",
    "az": "ariz,arizctapp",
    "ma": "mass,massappct",
    "in": "ind,indctapp",
    "tn": "tenn,tennctapp",
    "mo": "mo,moctapp",
    "md": "md,mdctspecapp",
    "wi": "wis,wisctapp",
    "co": "colo,coloctapp",
    "mn": "minn,minnctapp",
    "al": "ala,alactapp",
    "sc": "sc,scctapp",
    "la": "la,lactapp",
    "ky": "ky,kyctapp",
    "or": "or,orctapp",
    "ok": "okla,oklacivapp,oklacrimapp",
    "ct": "conn,connappct",
    "ia": "iowa,iowactapp",
    "ms": "miss,missctapp",
    "ar": "ark,arkctapp",
    "ks": "kan,kanctapp",
    "ut": "utah,utahctapp",
    "nv": "nev,nevapp",
    "nm": "nm,nmctapp",
    "ne": "neb,nebctapp",
    "wv": "wva",
    "id": "idaho,idahoctapp",
    "hi": "haw,hawapp",
    "me": "me",
    "nh": "nh",
    "ri": "ri",
    "mt": "mont",
    "de": "del,delch,delsuperct",
    "sd": "sd",
    "nd": "nd,ndctapp",
    "ak": "alaska,alaskactapp",
    "dc": "dc,dcctapp",
    "vt": "vt",
    "wy": "wyo",
    "scotus": "scotus",
    "federal": "ca1,ca2,ca3,ca4,ca5,ca6,ca7,ca8,ca9,ca10,ca11,cadc,cafc"
}

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def get_timestamp() -> str:
    """Get current UTC timestamp in ISO format"""
    return datetime.utcnow().isoformat() + "Z"

def get_state_bar_info(state: str) -> Dict[str, str]:
    """Get state bar information for a given state code"""
    state = state.upper()
    if state in STATE_BAR_INFO:
        return STATE_BAR_INFO[state]
    return {
        "name": f"{state} State Bar",
        "url": "https://www.americanbar.org/groups/legal_services/flh-home/",
        "instructions": "Visit the American Bar Association to find your state bar"
    }

def build_verification_url(state: str, bar_number: str) -> str:
    """Build the verification URL for a state, with direct linking if available"""
    state = state.upper()
    info = STATE_BAR_INFO.get(state, {})
    
    # California supports direct linking
    if state == "CA" and bar_number:
        return f"https://apps.calbar.ca.gov/attorney/Licensee/Detail/{bar_number}"
    
    # Return base URL for other states
    return info.get("url", "https://www.americanbar.org/groups/legal_services/flh-home/")

async def verify_california_attorney(
    bar_number: str,
    verification_url: str,
    info: Dict[str, str]
) -> VerifyAttorneyResponse:
    """
    Verify California attorney by attempting to scrape the state bar website.
    California provides direct links to attorney profiles without CAPTCHA.
    """
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9"
    }
    
    logger.info(f"Attempting to verify California attorney with bar number: {bar_number}")
    
    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT, follow_redirects=True) as client:
        try:
            # Try to fetch the attorney profile page
            response = await client.get(verification_url, headers=headers)
            response.raise_for_status()
            html_content = response.text
            
            # Check if the page indicates attorney not found
            if "not found" in html_content.lower() or "no results" in html_content.lower():
                logger.warning(f"California attorney not found: {bar_number}")
                return VerifyAttorneyResponse(
                    success=True,
                    verified=False,
                    status="Attorney bar number not found in California State Bar records. The bar number may be invalid or the attorney may not be licensed in California. Please verify the bar number is correct.",
                    name=None,
                    admission_date=None,
                    discipline_history=False,
                    verification_url=verification_url,
                    state_bar_name=info["name"],
                    instructions="The provided bar number was not found. Please check the number and visit the URL to search manually.",
                    retrieved_at=get_timestamp()
                )
            
            # Parse HTML content to extract status information
            if len(html_content) > 5000 and bar_number in html_content:
                logger.info(f"California attorney page found for bar number: {bar_number}")
                
                # Extract status from HTML - look for status after "License Status:" label
                html_lower = html_content.lower()
                
                # Determine if attorney is active
                is_active = None
                status_text = "Unknown"
                
                # Look for the license status section specifically - within the first 100 chars after "License Status:"
                if "license status:" in html_lower:
                    status_idx = html_lower.find("license status:")
                    # Only look in a narrow window to avoid picking up definitions table
                    status_section = html_lower[status_idx:status_idx+120]
                    
                    # Check for specific statuses - order matters!
                    if "inactive" in status_section:
                        is_active = False
                        status_text = "Inactive"
                    elif "suspended" in status_section:
                        is_active = False
                        status_text = "Suspended"
                    elif "disbarred" in status_section:
                        is_active = False
                        status_text = "Disbarred"
                    elif "retired" in status_section:
                        is_active = False
                        status_text = "Retired"
                    elif "resigned" in status_section:
                        is_active = False
                        status_text = "Resigned"
                    elif "active" in status_section:
                        # Active must be checked last to avoid matching "inactive"
                        is_active = True
                        status_text = "Active"
                
                # Check for disciplinary information in a targeted way
                # Look for "Public Reproval" or similar actual disciplinary notices
                has_discipline = False
                if "reproval" in html_lower or "probation" in html_lower:
                    has_discipline = True
                elif "disciplinary" in html_lower and "no public record" not in html_lower:
                    # Check if there's actual disciplinary content, not just a header
                    discipline_idx = html_lower.find("disciplinary")
                    discipline_context = html_lower[discipline_idx:discipline_idx+300]
                    if "record" in discipline_context and "none" not in discipline_context:
                        has_discipline = True
                
                # Build status message
                if is_active is True:
                    status_message = f"✓ VERIFIED ACTIVE: This California attorney (bar #{bar_number}) is currently ACTIVE and authorized to practice law."
                elif is_active is False:
                    status_message = f"✗ NOT ACTIVE: This California attorney (bar #{bar_number}) has status '{status_text}' and is NOT authorized to practice law."
                else:
                    status_message = f"California attorney profile found for bar number {bar_number}. Status could not be automatically determined. Visit the provided URL to view their current status."
                
                if has_discipline and is_active is True:
                    status_message += " WARNING: Disciplinary records exist - review the verification URL for details before proceeding."
                elif has_discipline:
                    status_message += " Disciplinary records may exist - see verification URL for details."
                
                logger.info(f"California attorney status: {bar_number} - Status: {status_text}, Verified: {is_active}, Discipline: {has_discipline}")
                
                return VerifyAttorneyResponse(
                    success=True,
                    verified=is_active,
                    status=status_message,
                    name=None,
                    admission_date=None,
                    discipline_history=has_discipline,
                    verification_url=verification_url,
                    state_bar_name=info["name"],
                    instructions=f"Complete verification details available at the provided URL. The California State Bar profile includes admission date, practice areas, contact information, and full disciplinary history.",
                    retrieved_at=get_timestamp()
                )
            
            # If we can't determine status, provide manual verification instructions
            logger.info(f"California attorney verification requires manual check for: {bar_number}")
            return VerifyAttorneyResponse(
                success=True,
                verified=None,
                status=f"Please verify this California attorney manually. The direct link to bar number {bar_number}'s profile has been provided. Click the URL to view their current license status, credentials, and disciplinary history.",
                name=None,
                admission_date=None,
                discipline_history=False,
                verification_url=verification_url,
                state_bar_name=info["name"],
                instructions="IMPORTANT: Visit the verification_url to access this attorney's official California State Bar profile. You will see their current status (Active/Inactive/Suspended), admission date, and any disciplinary actions. This is the authoritative source for California attorney verification.",
                retrieved_at=get_timestamp()
            )
            
        except httpx.HTTPError as e:
            logger.error(f"HTTP error verifying California attorney: {str(e)}")
            return VerifyAttorneyResponse(
                success=True,
                verified=None,
                status=f"Manual verification required for California bar number {bar_number}. A direct link to their State Bar profile has been provided. Visit the URL to confirm their license status and credentials.",
                name=None,
                admission_date=None,
                discipline_history=False,
                verification_url=verification_url,
                state_bar_name=info["name"],
                instructions="IMPORTANT: Click the verification_url to view this attorney's official profile on the California State Bar website. The profile includes current license status, admission date, and any disciplinary records.",
                retrieved_at=get_timestamp()
            )
        except Exception as e:
            logger.error(f"Error verifying California attorney: {str(e)}")
            return VerifyAttorneyResponse(
                success=True,
                verified=None,
                status=f"Manual verification required for California bar number {bar_number}. A direct link to their State Bar profile has been provided. Visit the URL to confirm their license status and credentials.",
                name=None,
                admission_date=None,
                discipline_history=False,
                verification_url=verification_url,
                state_bar_name=info["name"],
                instructions="IMPORTANT: Click the verification_url to view this attorney's official profile on the California State Bar website. The profile includes current license status, admission date, and any disciplinary records.",
                retrieved_at=get_timestamp()
            )

# ============================================================================
# COURTLISTENER API INTEGRATION
# ============================================================================

async def search_courtlistener(
    query: str,
    location: Optional[str] = None,
    date_after: Optional[str] = None,
    limit: int = 5
) -> CaseSearchResponse:
    """
    Search CourtListener for case law
    
    CourtListener API Docs: https://www.courtlistener.com/help/api/rest/
    """
    
    base_url = "https://www.courtlistener.com/api/rest/v4/search/"
    
    # Enhance query with location if provided
    enhanced_query = query
    if location:
        enhanced_query = f"{query} {location}"
    
    # Build search parameters
    params = {
        "q": enhanced_query,
        "type": "o",  # Search opinions
        "order_by": "score desc",
        "page_size": min(limit, 20)
    }
    
    # Add date filter if provided
    if date_after:
        params["filed_after"] = date_after
    
    # Build headers
    headers = {
        "User-Agent": "LegalNav-API/1.0 (IBM-DevDay-Hackathon)"
    }
    if COURTLISTENER_API_TOKEN:
        headers["Authorization"] = f"Token {COURTLISTENER_API_TOKEN}"
    
    logger.info(f"Searching CourtListener: query='{enhanced_query}', location='{location}', limit={limit}")
    
    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
        try:
            response = await client.get(base_url, params=params, headers=headers)
            response.raise_for_status()
            data = response.json()
            
            cases = []
            for result in data.get("results", [])[:limit]:
                # Extract citation (can be a list)
                citations = result.get("citation", [])
                citation = None
                if isinstance(citations, list) and citations:
                    citation = citations[0]
                elif isinstance(citations, str):
                    citation = citations
                
                # Extract snippet/summary
                snippet = result.get("snippet", "")
                if snippet:
                    # Clean up HTML tags from snippet
                    snippet = snippet.replace("<mark>", "**").replace("</mark>", "**")
                    snippet = snippet[:500] + "..." if len(snippet) > 500 else snippet
                
                # Build absolute URL
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
            
            logger.info(f"Found {len(cases)} cases out of {data.get('count', 0)} total")
            
            return CaseSearchResponse(
                success=True,
                cases=cases,
                total_results=data.get("count", 0),
                query_used=enhanced_query,
                source="CourtListener (Free Law Project)",
                source_url="https://www.courtlistener.com",
                retrieved_at=get_timestamp()
            )
            
        except httpx.HTTPStatusError as e:
            logger.error(f"CourtListener HTTP error: {e.response.status_code} - {e.response.text}")
            raise HTTPException(
                status_code=e.response.status_code,
                detail=f"CourtListener API error: {e.response.text}"
            )
        except httpx.TimeoutException:
            logger.error("CourtListener request timed out")
            raise HTTPException(
                status_code=504,
                detail="Search request timed out. Please try again with a simpler query."
            )
        except Exception as e:
            logger.error(f"CourtListener search failed: {str(e)}")
            raise HTTPException(
                status_code=500,
                detail=f"Search failed: {str(e)}"
            )

# ============================================================================
# API ENDPOINTS
# ============================================================================

@app.get("/", response_model=Dict[str, Any])
async def root():
    """
    Root endpoint - API information and health check
    
    Returns basic information about the LegalNav API including
    available endpoints and service status.
    """
    return {
        "service": "LegalNav Live API",
        "version": "1.0.0",
        "status": "running",
        "hackathon": "IBM Dev Day: AI Demystified 2026",
        "description": "Real-time legal data API for watsonx Orchestrate",
        "endpoints": {
            "documentation": "/docs",
            "health": "/api/v1/health",
            "search_cases": "/api/v1/cases/search",
            "verify_attorney": "/api/v1/attorneys/verify"
        },
        "data_sources": {
            "case_law": "CourtListener (Free Law Project)",
            "attorney_verification": "State Bar Associations"
        },
        "timestamp": get_timestamp()
    }

@app.get("/api/v1/health", response_model=HealthResponse)
async def health_check():
    """
    Health check endpoint
    
    Returns the current status of the API including whether
    external service credentials are configured.
    """
    return HealthResponse(
        status="healthy",
        service="LegalNav Live API",
        version="1.0.0",
        timestamp=get_timestamp(),
        courtlistener_configured=bool(COURTLISTENER_API_TOKEN)
    )

@app.post(
    "/api/v1/cases/search",
    response_model=CaseSearchResponse,
    responses={
        400: {"model": ErrorResponse, "description": "Invalid request parameters"},
        500: {"model": ErrorResponse, "description": "Server error"},
        504: {"model": ErrorResponse, "description": "Request timeout"}
    }
)
async def search_cases(request: CaseSearchRequest):
    """
    Search CourtListener for relevant case law and legal precedents.
    
    This endpoint searches the CourtListener database (Free Law Project),
    which contains over 8 million court opinions from federal and state courts.
    
    **Use Cases:**
    - Find cases related to tenant rights, evictions, habitability
    - Research employment law precedents
    - Find family law cases about custody, support
    - Search for civil rights cases
    - Research consumer protection cases
    
    **Tips for Better Results:**
    - Use specific legal terms (e.g., "implied warranty habitability" not "apartment problems")
    - Add jurisdiction for state-specific results
    - Use date filters for recent precedents
    
    **Example Queries:**
    - "tenant eviction retaliatory habitability"
    - "wrongful termination whistleblower at-will employment"
    - "custody modification best interest child"
    - "wage theft unpaid overtime FLSA"
    """
    return await search_courtlistener(
        query=request.query,
        location=request.location,
        date_after=request.date_after,
        limit=request.limit
    )

@app.post(
    "/api/v1/attorneys/verify",
    response_model=VerifyAttorneyResponse,
    responses={
        400: {"model": ErrorResponse, "description": "Invalid state code or bar number"}
    }
)
async def verify_attorney(request: VerifyAttorneyRequest):
    """
    Get verification information for an attorney's bar status.
    
    For California: Automatically fetches and verifies attorney data from the state bar.
    For other states: Provides verification URL for manual checking.
    
    **What This Returns:**
    - For CA: Real-time verification status, attorney name, and details
    - For other states: Verification URL with clear instructions for manual verification
    
    **Supported for All 50 States + DC**
    """
    state = request.state.upper()
    bar_number = request.bar_number.strip()
    
    # Validate state code
    if state not in STATE_BAR_INFO:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid state code: {state}. Use two-letter state codes (e.g., CA, TX, NY)."
        )
    
    info = STATE_BAR_INFO[state]
    verification_url = build_verification_url(state, bar_number)
    
    logger.info(f"Attorney verification request: state={state}, bar_number={bar_number}")
    
    # For California, fetch actual verification data
    if state == "CA":
        return await verify_california_attorney(bar_number, verification_url, info)
    
    # For all other states, return URL with clear instructions
    return VerifyAttorneyResponse(
        success=True,
        verified=None,
        status=f"Manual verification required. Please visit the provided URL to verify this attorney's bar status with the {info['name']}. The URL will show their current license status, admission date, and any disciplinary history.",
        name=None,
        admission_date=None,
        discipline_history=False,
        verification_url=verification_url,
        state_bar_name=info["name"],
        instructions=f"IMPORTANT: You must visit the verification_url to confirm this attorney's credentials. The {info['name']} maintains the official record. {info['instructions']}",
        retrieved_at=get_timestamp()
    )

# ============================================================================
# ADDITIONAL ENDPOINTS FOR WATSONX ORCHESTRATE
# ============================================================================

@app.get(
    "/api/v1/jurisdictions",
    response_model=Dict[str, Any]
)
async def list_jurisdictions():
    """
    List available court jurisdictions for case search.
    
    Returns a mapping of jurisdiction codes that can be used
    with the case search endpoint.
    """
    return {
        "jurisdictions": {
            code: {"courts": courts}
            for code, courts in COURTLISTENER_JURISDICTIONS.items()
        },
        "common": {
            "scotus": "United States Supreme Court",
            "federal": "All Federal Circuit Courts",
            "ca": "California State Courts",
            "tx": "Texas State Courts",
            "ny": "New York State Courts",
            "fl": "Florida State Courts"
        },
        "note": "Use lowercase jurisdiction codes in the search request"
    }

@app.get(
    "/api/v1/states",
    response_model=Dict[str, Any]
)
async def list_states():
    """
    List all supported states for attorney verification.
    
    Returns information about all 50 states + DC including
    their state bar names and verification URLs.
    """
    return {
        "states": {
            code: {
                "name": info["name"],
                "verification_url": info["url"]
            }
            for code, info in STATE_BAR_INFO.items()
        },
        "total": len(STATE_BAR_INFO),
        "note": "Use uppercase state codes (e.g., CA, TX, NY)"
    }

# ============================================================================
# ERROR HANDLERS
# ============================================================================

@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc):
    """Handle HTTP exceptions with consistent format"""
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "success": False,
            "error": exc.detail,
            "error_code": f"HTTP_{exc.status_code}",
            "timestamp": get_timestamp()
        }
    )

@app.exception_handler(Exception)
async def general_exception_handler(request, exc):
    """Handle unexpected exceptions"""
    logger.error(f"Unexpected error: {str(exc)}")
    return JSONResponse(
        status_code=500,
        content={
            "success": False,
            "error": "An unexpected error occurred",
            "error_code": "INTERNAL_ERROR",
            "timestamp": get_timestamp()
        }
    )

# ============================================================================
# MAIN ENTRY POINT
# ============================================================================

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=port,
        reload=os.getenv("ENVIRONMENT", "production") == "development"
    )
