import axios from 'axios'

const api = axios.create({ baseURL: '/api' })

// Settings
export const getAllSettings     = ()      => api.get('/settings/').then(r => r.data)
export const updateSetting      = (k, v)  => api.put(`/settings/${k}`, { value: v }).then(r => r.data)
export const getAIProviders     = ()      => api.get('/settings/ai-providers').then(r => r.data)

// Real automation mode
export const getLiveMode        = ()      => api.get('/settings/live-mode').then(r => r.data)
export const setLiveMode        = (on)    => api.put('/settings/live-mode', { enabled: !!on }).then(r => r.data)

// LinkedIn debug
export const linkedinDiagnose   = ()      => api.get('/linkedin/diagnose').then(r => r.data)
export const testLinkedinSearch = (b)     => api.post('/linkedin/test-search', b).then(r => r.data)
export const testLinkedinApply  = (b)     => api.post('/linkedin/test-apply', b).then(r => r.data)

// LinkedIn session
export const getLinkedInSessionStatus = () => api.get('/settings/linkedin-session').then(r => r.data)
export const openLinkedInLogin        = () => api.post('/settings/linkedin-session/open').then(r => r.data)
export const confirmLinkedInLogin     = () => api.post('/settings/linkedin-session/confirm').then(r => r.data)
export const checkLoginStatus         = () => api.get('/settings/linkedin-session/login-status').then(r => r.data)
export const verifyLinkedInSession    = () => api.post('/settings/linkedin-session/verify').then(r => r.data)
export const clearLinkedInSession     = () => api.delete('/settings/linkedin-session').then(r => r.data)

// Profile (LinkedIn)
export const getProfile     = () => api.get('/profile/').then(r => r.data)
export const importProfile  = () => api.post('/profile/import').then(r => r.data)
export const getProfileStatus = () => api.get('/profile/status').then(r => r.data)
export const logoutProfile  = () => api.post('/profile/logout').then(r => r.data)
export const getAuthProviders = () => api.get('/auth/providers').then(r => r.data)
export const startEmailSignup = (email) => api.post('/auth/email/start', { email }).then(r => r.data)
export const verifyEmailSignup = (email, code) => api.post('/auth/email/verify', { email, code }).then(r => r.data)

// Job sources
export const getJobSources = () => api.get('/sources/').then(r => r.data)
export const connectJobSource = (id) => api.post(`/sources/${id}/connect`).then(r => r.data)
export const disconnectJobSource = (id) => api.delete(`/sources/${id}`).then(r => r.data)

// Dashboard
export const getDashboardStats = () => api.get('/dashboard/stats').then(r => r.data)

// CV
export const uploadCV  = (form) => api.post('/cv/upload', form, { headers: { 'Content-Type': 'multipart/form-data' } }).then(r => r.data)
export const getCV     = ()     => api.get('/cv/').then(r => r.data)
export const clearCV   = ()     => api.delete('/cv/').then(r => r.data)

// Chat (preference intake)
export const getChat   = ()         => api.get('/chat/').then(r => r.data)
export const sendChat  = (msg, opts={}) => api.post('/chat/', { message: msg, ...opts }).then(r => r.data)
export const resetChat = ()         => api.post('/chat/', { reset: true }).then(r => r.data)

// Jobs
export const getJobs            = ()      => api.get('/jobs/').then(r => r.data)
export const getApplications    = ()      => api.get('/jobs/applications').then(r => r.data)
export const getAppliedJobs     = ()      => api.get('/jobs/applied').then(r => r.data)
export const getPendingJobs     = ()      => api.get('/jobs/pending').then(r => r.data)
export const getExternalJobs    = ()      => api.get('/jobs/external').then(r => r.data)
export const answerPendingJob   = (id, answer, save_to_bank=true) =>
  api.post(`/jobs/${id}/answer`, { answer, save_to_bank }).then(r => r.data)
export const dismissJob         = (id)    => api.delete(`/jobs/${id}`).then(r => r.data)

// Answers
export const getAnswers    = ()        => api.get('/answers/').then(r => r.data)
export const saveAnswer    = (data)    => api.post('/answers/', data).then(r => r.data)
export const deleteAnswer  = (id)     => api.delete(`/answers/${id}`).then(r => r.data)

// Automation
export const getAutomationStatus  = () => api.get('/automation/status').then(r => r.data)
export const startAutomation      = () => api.post('/automation/start').then(r => r.data)
export const stopAutomation       = () => api.post('/automation/stop').then(r => r.data)
export const clearJobs            = () => api.post('/automation/clear-jobs').then(r => r.data)

export default api
