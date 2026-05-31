import { defineStore } from 'pinia'
import { ref, computed } from 'vue'

export interface Profile {
  id: number
  name: string
  tools: string[]
  profile_prompt: string
  temperature: number
  top_p: number
  top_k: number
  frequency_penalty: number
  presence_penalty: number
}

export const useProfileStore = defineStore('profile', () => {
  const profiles = ref<Profile[]>([])
  const activeProfileId = ref<number | null>(null)

  async function loadProfiles() {
    const res = await fetch('/api/profiles/')
    let data = await res.json()
    // 确保每个角色都有生成参数默认值（后端可能尚未返回这些字段）
    data = data.map((p: any) => ({
      ...p,
      temperature: p.temperature ?? 1,
      top_p: p.top_p ?? 1,
      top_k: p.top_k ?? 40,
      frequency_penalty: p.frequency_penalty ?? 0,
      presence_penalty: p.presence_penalty ?? 0,
    }))
    profiles.value = data
    if (!activeProfileId.value || !profiles.value.find(p => p.id === activeProfileId.value)) {
      if (profiles.value.length > 0) activeProfileId.value = profiles.value[0].id
    }
  }

  async function createProfile(
    name: string,
    tools: string[] = [],
    profile_prompt: string = '',
    temperature: number = 1,
    top_p: number = 1,
    top_k: number = 40,
    frequency_penalty: number = 0,
    presence_penalty: number = 0
  ) {
    const res = await fetch('/api/profiles/', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name, tools, profile_prompt, temperature, top_p, top_k, frequency_penalty, presence_penalty })
    })
    const newProfile = await res.json()
    // 补全默认值（以防后端未完整返回）
    const completeProfile: Profile = {
      ...newProfile,
      temperature: newProfile.temperature ?? 1,
      top_p: newProfile.top_p ?? 1,
      top_k: newProfile.top_k ?? 40,
      frequency_penalty: newProfile.frequency_penalty ?? 0,
      presence_penalty: newProfile.presence_penalty ?? 0,
    }
    profiles.value.push(completeProfile)
    activeProfileId.value = completeProfile.id
    return completeProfile
  }

  async function updateProfile(
    id: number,
    name: string,
    tools: string[],
    profile_prompt: string = '',
    temperature?: number,
    top_p?: number,
    top_k?: number,
    frequency_penalty?: number,
    presence_penalty?: number
  ) {
    await fetch(`/api/profiles/${id}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name, tools, profile_prompt, temperature, top_p, top_k, frequency_penalty, presence_penalty })
    })
    const profile = profiles.value.find(p => p.id === id)
    if (profile) {
      profile.name = name
      profile.tools = tools
      profile.profile_prompt = profile_prompt
      if (temperature !== undefined) profile.temperature = temperature
      if (top_p !== undefined) profile.top_p = top_p
      if (top_k !== undefined) profile.top_k = top_k
      if (frequency_penalty !== undefined) profile.frequency_penalty = frequency_penalty
      if (presence_penalty !== undefined) profile.presence_penalty = presence_penalty
    }
  }

  async function deleteProfile(id: number) {
    await fetch(`/api/profiles/${id}`, { method: 'DELETE' })
    profiles.value = profiles.value.filter(p => p.id !== id)
    if (activeProfileId.value === id) {
      activeProfileId.value = profiles.value[0]?.id ?? null
    }
  }

  const activeProfile = computed(() => profiles.value.find(p => p.id === activeProfileId.value))

  const activeToolsSet = computed(() => {
    const p = activeProfile.value
    return p ? new Set(p.tools) : new Set<string>()
  })

  return { profiles, activeProfileId, activeProfile, activeToolsSet, loadProfiles, createProfile, updateProfile, deleteProfile }
})