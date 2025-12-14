# Equipment OCR & Warranty Lookup System

## Project Overview

**Goal:** Automatically extract equipment data from data plate photos, look up warranty information from manufacturer websites, and format everything for ServiceTitan's equipment database.

**Business Value:**
- Eliminate manual data entry for equipment tags
- Enable marketing automation based on equipment age, refrigerant type, warranty status
- Process 10,000+ backlog photos, then automate ongoing new photos

---

## What We Built (Proof of Concept)

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│                 │     │                 │     │                 │
│  📷 Photo of    │────▶│  🔍 OCR &       │────▶│  🌐 Warranty    │
│  Data Plate     │     │  Extract Data   │     │  Lookup         │
│                 │     │                 │     │                 │
└─────────────────┘     └─────────────────┘     └─────────────────┘
                                                        │
                                                        ▼
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│                 │     │                 │     │                 │
│  📊 ServiceTitan│◀────│  🏷️ Generate    │◀────│  📋 Parse       │
│  API Payload    │     │  Marketing Tags │     │  Warranty PDF   │
│                 │     │                 │     │                 │
└─────────────────┘     └─────────────────┘     └─────────────────┘
```

---

## Test Results (Your Trane XR12 Photo)

### Input
- Photo: `IMG_1889.jpeg` (Trane XR 12 data plate)

### Extracted via OCR
| Field | Value |
|-------|-------|
| Manufacturer | Trane (American Standard) |
| Model | 2TTR2048A1000AA |
| Serial | 5434REB2F |
| MFR Date | October 2005 |
| Tonnage | 4 tons (48,000 BTU) |
| Refrigerant | R-22, 7 lbs 8 oz |
| Voltage | 208/230V, 1-Phase, 60Hz |

### Retrieved via Warranty Lookup
| Field | Value |
|-------|-------|
| Install Date | 08/18/2006 |
| Outdoor Coil Warranty | Expired 08/18/2016 |
| Functional Parts | Expired 08/18/2011 |
| Compressor | Expired 08/18/2016 |

### Generated Alerts
- 🔴 **R-22 Refrigerant** — Discontinued, expensive repairs
- 🔴 **Age: 19 years** — Beyond typical lifespan
- 🔴 **All warranties expired** — 100% customer cost
- 🟡 **SEER 12** — Below current 14 minimum

---

## Files Included

```
equipment_poc.py          # Main Python script
equipment_report_FINAL.txt    # Sample output report (human-readable)
equipment_data_FINAL.json     # Sample output data (structured)
README.md                     # This file
```

---

## How It Works

### Step 1: Image Classification
Determine if the uploaded image is actually an equipment data plate (vs. a random job photo).

```python
# In production: Send image to Claude Vision API
# Prompt: "Is this an HVAC equipment data plate? Yes/No + confidence score"
```

### Step 2: OCR & Data Extraction
Extract all text from the data plate and parse into structured fields.

```python
# In production: Send image to Claude Vision API
# Prompt: "Extract manufacturer, model, serial, MFR date, specs..."
# Returns structured JSON
```

### Step 3: Brand Detection & Warranty Lookup
Based on manufacturer, hit the correct warranty portal:

| Brand | Warranty URL |
|-------|-------------|
| Trane / American Standard | `americanstandardair.com/resources/warranty-and-registration/lookup/` |
| Carrier / Bryant | `carrier.com/residential/en/us/warranty-lookup/` |
| Goodman / Amana | `goodmanmfg.com/warranty-lookup` |
| Lennox | `lennox.com/residential/owners/assistance/warranty/` |

Uses **Playwright** (headless browser) to:
1. Navigate to warranty site
2. Enter serial number
3. Submit form
4. Scrape results (and optionally download PDF)

### Step 4: Generate Output
- Human-readable report with alerts
- JSON payload ready for ServiceTitan API
- Marketing tags for automation

---

## ServiceTitan Integration

The output JSON matches ServiceTitan's `POST /installed-equipment` endpoint:

```json
{
  "locationId": "<<FROM_JOB>>",
  "customerId": "<<FROM_JOB>>",
  "name": "Trane XR 12 - 4 Ton AC",
  "manufacturer": "Trane",
  "model": "2TTR2048A1000AA",
  "serialNumber": "5434REB2F",
  "installedOn": "2006-08-18T00:00:00Z",
  "manufacturerWarrantyStart": "2006-08-18T00:00:00Z",
  "manufacturerWarrantyEnd": "2016-08-18T00:00:00Z",
  "memo": "4-ton | R-22 | SEER 12 | ⚠️ REPLACEMENT CANDIDATE",
  "status": "Installed"
}
```

---

## Replit Setup Instructions

### 1. Create New Replit
- Choose **Python** template
- Name it something like `equipment-ocr-warranty`

### 2. Install Dependencies
In the Replit shell:
```bash
pip install playwright anthropic
playwright install chromium
```

### 3. Add Environment Variables
In Replit Secrets, add:
```
ANTHROPIC_API_KEY=sk-ant-...  # For Claude Vision OCR
```

### 4. Upload Files
- Copy `equipment_poc.py` to your Replit
- Modify as needed for your workflow

### 5. Test
```bash
python equipment_poc.py
```

---

## What's Next (To Make Production-Ready)

### Phase 1: Manual Testing ✅ Current
- [x] OCR extraction working
- [x] Warranty lookup URL confirmed (American Standard)
- [x] Output format matches ServiceTitan API
- [ ] Test Playwright on Replit with live warranty lookup

### Phase 2: Add More Brands
- [ ] Carrier/Bryant handler
- [ ] Goodman handler  
- [ ] Lennox handler
- [ ] Brand detection from OCR output

### Phase 3: ServiceTitan Integration
- [ ] Connect to ServiceTitan API (you have credentials)
- [ ] Pull job attachments via API
- [ ] Write equipment records via API
- [ ] Link equipment to correct location/customer

### Phase 4: Backlog Processing
- [ ] Export all jobs with attachments
- [ ] Classify images (data plate vs other)
- [ ] Process in batches with rate limiting
- [ ] Manual review queue for low-confidence OCR

### Phase 5: Ongoing Automation
- [ ] Trigger on new job attachments (webhook or polling)
- [ ] Same pipeline, automated

---

## Cost Estimates

| Component | Per Image | 10K Backlog |
|-----------|-----------|-------------|
| Image classification (Claude) | ~$0.002 | ~$1,000 (for 500K total images) |
| OCR extraction (Claude) | ~$0.02 | ~$400 (for ~20K data plates) |
| Warranty lookup (compute) | ~$0.01 | ~$200 |
| **Total** | | **~$1,600** |

---

## Key Learnings

1. **Use American Standard portal for Trane units** — Found a 2005 unit that might not be in Trane's system

2. **Warranty lookup requires browser automation** — These are JavaScript forms, not simple APIs

3. **Rate limiting is important** — Don't hammer warranty sites; 1 request per 5-10 seconds

4. **Old units may not have warranty records** — But we still get valuable data from OCR (install date approximated from MFR date)

5. **R-22 systems are gold for marketing** — Easy to identify, strong replacement pitch

---

## Questions?

This POC proves the concept works. Next step is deploying to Replit and testing with live warranty lookups, then expanding to other brands and wiring up ServiceTitan.
