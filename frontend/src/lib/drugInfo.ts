import {
  Pill,
  Dna,
  Target,
  Brain,
  Syringe,
  FlaskConical,
  Heart,
  Shield,
} from 'lucide-react'

interface DrugInfo {
  brandName: string
  genericName: string
  category: string
  icon: typeof Pill
  color: string
}

const drugDatabase: Record<string, DrugInfo> = {
  carvykti: {
    brandName: 'Carvykti',
    genericName: 'ciltacabtagene autoleucel',
    category: 'CAR-T Therapy',
    icon: Dna,
    color: 'text-text-secondary bg-surface-tertiary',
  },
  ciltacabtagene_autoleucel: {
    brandName: 'Carvykti',
    genericName: 'ciltacabtagene autoleucel',
    category: 'CAR-T Therapy',
    icon: Dna,
    color: 'text-text-secondary bg-surface-tertiary',
  },
  spinraza: {
    brandName: 'Spinraza',
    genericName: 'nusinersen',
    category: 'SMA Treatment',
    icon: Brain,
    color: 'text-text-secondary bg-surface-tertiary',
  },
  nusinersen: {
    brandName: 'Spinraza',
    genericName: 'nusinersen',
    category: 'SMA Treatment',
    icon: Brain,
    color: 'text-text-secondary bg-surface-tertiary',
  },
  palbociclib: {
    brandName: 'Ibrance',
    genericName: 'palbociclib',
    category: 'Oncology',
    icon: Target,
    color: 'text-text-secondary bg-surface-tertiary',
  },
  ibrance: {
    brandName: 'Ibrance',
    genericName: 'palbociclib',
    category: 'Oncology',
    icon: Target,
    color: 'text-text-secondary bg-surface-tertiary',
  },
  infliximab: {
    brandName: 'Remicade',
    genericName: 'infliximab',
    category: 'Biologic',
    icon: FlaskConical,
    color: 'text-text-secondary bg-surface-tertiary',
  },
  remicade: {
    brandName: 'Remicade',
    genericName: 'infliximab',
    category: 'Biologic',
    icon: FlaskConical,
    color: 'text-text-secondary bg-surface-tertiary',
  },
  breyanzi: {
    brandName: 'Breyanzi',
    genericName: 'lisocabtagene maraleucel',
    category: 'CAR-T Therapy',
    icon: Dna,
    color: 'text-text-secondary bg-surface-tertiary',
  },
  lisocabtagene_maraleucel: {
    brandName: 'Breyanzi',
    genericName: 'lisocabtagene maraleucel',
    category: 'CAR-T Therapy',
    icon: Dna,
    color: 'text-text-secondary bg-surface-tertiary',
  },
  adalimumab: {
    brandName: 'Humira',
    genericName: 'adalimumab',
    category: 'Biologic',
    icon: FlaskConical,
    color: 'text-text-secondary bg-surface-tertiary',
  },
  humira: {
    brandName: 'Humira',
    genericName: 'adalimumab',
    category: 'Biologic',
    icon: FlaskConical,
    color: 'text-text-secondary bg-surface-tertiary',
  },
  rituximab: {
    brandName: 'Rituxan',
    genericName: 'rituximab',
    category: 'Biologic',
    icon: Syringe,
    color: 'text-text-secondary bg-surface-tertiary',
  },
  trastuzumab: {
    brandName: 'Herceptin',
    genericName: 'trastuzumab',
    category: 'Oncology',
    icon: Target,
    color: 'text-text-secondary bg-surface-tertiary',
  },
  pembrolizumab: {
    brandName: 'Keytruda',
    genericName: 'pembrolizumab',
    category: 'Immuno-Oncology',
    icon: Shield,
    color: 'text-text-secondary bg-surface-tertiary',
  },
  nivolumab: {
    brandName: 'Opdivo',
    genericName: 'nivolumab',
    category: 'Immuno-Oncology',
    icon: Shield,
    color: 'text-text-secondary bg-surface-tertiary',
  },
  etanercept: {
    brandName: 'Enbrel',
    genericName: 'etanercept',
    category: 'Biologic',
    icon: FlaskConical,
    color: 'text-text-secondary bg-surface-tertiary',
  },
  ocrelizumab: {
    brandName: 'Ocrevus',
    genericName: 'ocrelizumab',
    category: 'Neurology',
    icon: Brain,
    color: 'text-text-secondary bg-surface-tertiary',
  },
  bevacizumab: {
    brandName: 'Avastin',
    genericName: 'bevacizumab',
    category: 'Oncology',
    icon: Target,
    color: 'text-text-secondary bg-surface-tertiary',
  },
  lenalidomide: {
    brandName: 'Revlimid',
    genericName: 'lenalidomide',
    category: 'Oncology',
    icon: Target,
    color: 'text-text-secondary bg-surface-tertiary',
  },
  ustekinumab: {
    brandName: 'Stelara',
    genericName: 'ustekinumab',
    category: 'Biologic',
    icon: FlaskConical,
    color: 'text-text-secondary bg-surface-tertiary',
  },
  dupilumab: {
    brandName: 'Dupixent',
    genericName: 'dupilumab',
    category: 'Biologic',
    icon: Heart,
    color: 'text-text-secondary bg-surface-tertiary',
  },
}

const defaultDrugInfo: DrugInfo = {
  brandName: '',
  genericName: '',
  category: 'Specialty Drug',
  icon: Pill,
  color: 'text-text-secondary bg-surface-tertiary',
}

export function getDrugInfo(rawName: string): DrugInfo {
  const key = rawName.toLowerCase().trim().replace(/\s+/g, '_')
  const info = drugDatabase[key]
  if (info) return info

  const brandName = rawName
    .replace(/_/g, ' ')
    .replace(/\b\w/g, c => c.toUpperCase())

  return {
    ...defaultDrugInfo,
    brandName,
    genericName: rawName.replace(/_/g, ' '),
  }
}

interface PayerInfo {
  displayName: string
  abbreviation: string
  color: string
}

const payerDatabase: Record<string, PayerInfo> = {
  bcbs: {
    displayName: 'Blue Cross Blue Shield',
    abbreviation: 'BCBS',
    color: 'bg-text-quaternary',
  },
  cigna: {
    displayName: 'Cigna Healthcare',
    abbreviation: 'CIGNA',
    color: 'bg-text-quaternary',
  },
  aetna: {
    displayName: 'Aetna',
    abbreviation: 'AETNA',
    color: 'bg-text-quaternary',
  },
  unitedhealthcare: {
    displayName: 'UnitedHealthcare',
    abbreviation: 'UHC',
    color: 'bg-text-quaternary',
  },
  uhc: {
    displayName: 'UnitedHealthcare',
    abbreviation: 'UHC',
    color: 'bg-text-quaternary',
  },
  humana: {
    displayName: 'Humana',
    abbreviation: 'HUM',
    color: 'bg-text-quaternary',
  },
  anthem: {
    displayName: 'Anthem',
    abbreviation: 'ANTM',
    color: 'bg-text-quaternary',
  },
  kaiser: {
    displayName: 'Kaiser Permanente',
    abbreviation: 'KP',
    color: 'bg-text-quaternary',
  },
  centene: {
    displayName: 'Centene',
    abbreviation: 'CNC',
    color: 'bg-text-quaternary',
  },
  molina: {
    displayName: 'Molina Healthcare',
    abbreviation: 'MOH',
    color: 'bg-text-quaternary',
  },
  medicaid: {
    displayName: 'Medicaid',
    abbreviation: 'MCAID',
    color: 'bg-text-quaternary',
  },
  medicare: {
    displayName: 'Medicare',
    abbreviation: 'MCARE',
    color: 'bg-text-quaternary',
  },
}

export function getPayerInfo(rawName: string): PayerInfo {
  const key = rawName.toLowerCase().trim().replace(/[\s_-]+/g, '')
  const info = payerDatabase[key]
  if (info) return info

  return {
    displayName: rawName.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase()),
    abbreviation: rawName.toUpperCase().slice(0, 5),
    color: 'bg-text-quaternary',
  }
}

export function formatPayerName(rawName: string): string {
  return getPayerInfo(rawName).abbreviation
}

export function formatMedicationName(rawName: string): string {
  return getDrugInfo(rawName).brandName
}
