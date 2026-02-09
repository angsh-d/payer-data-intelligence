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
    color: 'text-accent-purple bg-accent-purple/10',
  },
  ciltacabtagene_autoleucel: {
    brandName: 'Carvykti',
    genericName: 'ciltacabtagene autoleucel',
    category: 'CAR-T Therapy',
    icon: Dna,
    color: 'text-accent-purple bg-accent-purple/10',
  },
  spinraza: {
    brandName: 'Spinraza',
    genericName: 'nusinersen',
    category: 'SMA Treatment',
    icon: Brain,
    color: 'text-accent-blue bg-accent-blue/10',
  },
  nusinersen: {
    brandName: 'Spinraza',
    genericName: 'nusinersen',
    category: 'SMA Treatment',
    icon: Brain,
    color: 'text-accent-blue bg-accent-blue/10',
  },
  palbociclib: {
    brandName: 'Ibrance',
    genericName: 'palbociclib',
    category: 'Oncology',
    icon: Target,
    color: 'text-accent-red bg-accent-red/10',
  },
  ibrance: {
    brandName: 'Ibrance',
    genericName: 'palbociclib',
    category: 'Oncology',
    icon: Target,
    color: 'text-accent-red bg-accent-red/10',
  },
  infliximab: {
    brandName: 'Remicade',
    genericName: 'infliximab',
    category: 'Biologic',
    icon: FlaskConical,
    color: 'text-accent-green bg-accent-green/10',
  },
  remicade: {
    brandName: 'Remicade',
    genericName: 'infliximab',
    category: 'Biologic',
    icon: FlaskConical,
    color: 'text-accent-green bg-accent-green/10',
  },
  breyanzi: {
    brandName: 'Breyanzi',
    genericName: 'lisocabtagene maraleucel',
    category: 'CAR-T Therapy',
    icon: Dna,
    color: 'text-accent-purple bg-accent-purple/10',
  },
  lisocabtagene_maraleucel: {
    brandName: 'Breyanzi',
    genericName: 'lisocabtagene maraleucel',
    category: 'CAR-T Therapy',
    icon: Dna,
    color: 'text-accent-purple bg-accent-purple/10',
  },
  adalimumab: {
    brandName: 'Humira',
    genericName: 'adalimumab',
    category: 'Biologic',
    icon: FlaskConical,
    color: 'text-accent-green bg-accent-green/10',
  },
  humira: {
    brandName: 'Humira',
    genericName: 'adalimumab',
    category: 'Biologic',
    icon: FlaskConical,
    color: 'text-accent-green bg-accent-green/10',
  },
  rituximab: {
    brandName: 'Rituxan',
    genericName: 'rituximab',
    category: 'Biologic',
    icon: Syringe,
    color: 'text-accent-amber bg-accent-amber/10',
  },
  trastuzumab: {
    brandName: 'Herceptin',
    genericName: 'trastuzumab',
    category: 'Oncology',
    icon: Target,
    color: 'text-accent-red bg-accent-red/10',
  },
  pembrolizumab: {
    brandName: 'Keytruda',
    genericName: 'pembrolizumab',
    category: 'Immuno-Oncology',
    icon: Shield,
    color: 'text-accent-blue bg-accent-blue/10',
  },
  nivolumab: {
    brandName: 'Opdivo',
    genericName: 'nivolumab',
    category: 'Immuno-Oncology',
    icon: Shield,
    color: 'text-accent-blue bg-accent-blue/10',
  },
  etanercept: {
    brandName: 'Enbrel',
    genericName: 'etanercept',
    category: 'Biologic',
    icon: FlaskConical,
    color: 'text-accent-green bg-accent-green/10',
  },
  ocrelizumab: {
    brandName: 'Ocrevus',
    genericName: 'ocrelizumab',
    category: 'Neurology',
    icon: Brain,
    color: 'text-accent-blue bg-accent-blue/10',
  },
  bevacizumab: {
    brandName: 'Avastin',
    genericName: 'bevacizumab',
    category: 'Oncology',
    icon: Target,
    color: 'text-accent-red bg-accent-red/10',
  },
  lenalidomide: {
    brandName: 'Revlimid',
    genericName: 'lenalidomide',
    category: 'Oncology',
    icon: Target,
    color: 'text-accent-red bg-accent-red/10',
  },
  ustekinumab: {
    brandName: 'Stelara',
    genericName: 'ustekinumab',
    category: 'Biologic',
    icon: FlaskConical,
    color: 'text-accent-green bg-accent-green/10',
  },
  dupilumab: {
    brandName: 'Dupixent',
    genericName: 'dupilumab',
    category: 'Biologic',
    icon: Heart,
    color: 'text-accent-amber bg-accent-amber/10',
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
    color: 'bg-blue-500',
  },
  cigna: {
    displayName: 'Cigna Healthcare',
    abbreviation: 'CIGNA',
    color: 'bg-orange-500',
  },
  aetna: {
    displayName: 'Aetna',
    abbreviation: 'AETNA',
    color: 'bg-purple-600',
  },
  unitedhealthcare: {
    displayName: 'UnitedHealthcare',
    abbreviation: 'UHC',
    color: 'bg-sky-600',
  },
  uhc: {
    displayName: 'UnitedHealthcare',
    abbreviation: 'UHC',
    color: 'bg-sky-600',
  },
  humana: {
    displayName: 'Humana',
    abbreviation: 'HUM',
    color: 'bg-green-600',
  },
  anthem: {
    displayName: 'Anthem',
    abbreviation: 'ANTM',
    color: 'bg-indigo-600',
  },
  kaiser: {
    displayName: 'Kaiser Permanente',
    abbreviation: 'KP',
    color: 'bg-amber-600',
  },
  centene: {
    displayName: 'Centene',
    abbreviation: 'CNC',
    color: 'bg-teal-600',
  },
  molina: {
    displayName: 'Molina Healthcare',
    abbreviation: 'MOH',
    color: 'bg-rose-600',
  },
  medicaid: {
    displayName: 'Medicaid',
    abbreviation: 'MCAID',
    color: 'bg-emerald-600',
  },
  medicare: {
    displayName: 'Medicare',
    abbreviation: 'MCARE',
    color: 'bg-cyan-600',
  },
}

export function getPayerInfo(rawName: string): PayerInfo {
  const key = rawName.toLowerCase().trim().replace(/[\s_-]+/g, '')
  const info = payerDatabase[key]
  if (info) return info

  return {
    displayName: rawName.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase()),
    abbreviation: rawName.toUpperCase().slice(0, 5),
    color: 'bg-gray-500',
  }
}

export function formatPayerName(rawName: string): string {
  return getPayerInfo(rawName).abbreviation
}

export function formatMedicationName(rawName: string): string {
  return getDrugInfo(rawName).brandName
}
