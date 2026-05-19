(function () {
  const form = document.querySelector('[data-contact-form]')
  const status = document.querySelector('[data-contact-status]')
  if (!form || !status) return

  form.addEventListener('submit', async (event) => {
    event.preventDefault()

    const submit = form.querySelector('button[type="submit"]')
    const data = new FormData(form)
    const payload = {
      name: String(data.get('name') || ''),
      email: String(data.get('email') || ''),
      company: String(data.get('company') || ''),
      role: String(data.get('role') || ''),
      useCase: String(data.get('useCase') || ''),
      wantsSlackInvite: data.get('wantsSlackInvite') === 'true',
    }

    status.textContent = ''
    submit.disabled = true

    try {
      const response = await fetch('/api/contact', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      })

      if (!response.ok) {
        const body = await response.json().catch(() => ({}))
        throw new Error(body.error || 'Submission failed')
      }

      form.reset()
      status.textContent = "Thanks. We'll follow up soon."
    } catch (error) {
      status.textContent =
        error instanceof Error ? error.message : 'Submission failed'
    } finally {
      submit.disabled = false
    }
  })
})()
