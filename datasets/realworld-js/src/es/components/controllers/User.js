// @ts-check

/* global HTMLElement */
/* global AbortController */
/* global CustomEvent */
/* global fetch */

/**
 * https://github.com/gothinkster/realworld/tree/master/api#authentication
 *
 * @typedef {{ email: string, password: string }} loginUserEventDetail
 */

/**
 * https://github.com/gothinkster/realworld/tree/master/api#authentication
 *
 * @typedef {{
      fetch: Promise<import("../../helpers/Interfaces.js").User>
      updated?: Boolean
    }} UserEventDetail
 */

/**
 * https://github.com/gothinkster/realworld/tree/master/api#authentication
 *
 * @typedef {{
  fetch: Promise<import("../../helpers/Interfaces.js").Profile>
}} ProfileEventDetail
*/

import { Environment } from '../../helpers/Environment.js'

/**
 * https://github.com/gothinkster/realworld/tree/master/api#get-article
 * As a controller, this component becomes a store and organizes events
 * dispatches: 'user' on 'loginUser'
 * dispatches: 'user' on 'registerUser'
 * dispatches: 'user' on 'updateUser'
 * dispatches: 'user' on 'getUser'
 * dispatches: 'user' (reject) on 'logoutUser'
 * dispatches: 'profile' on 'getProfile'
 *
 * @export
 * @class User
 */
export default class User extends HTMLElement {
  constructor () {
    super()

    /**
     * Used to cancel ongoing, older fetches
     * this makes sense, if you only expect one and most recent true result and not multiple
     *
     * @type {AbortController | null}
     */
    this.abortController = this.abortControllerProfile = null

    /**
     * Listens to the event name/typeArg: 'loginUser'
     *
     * @param {CustomEvent & {detail: loginUserEventDetail}} event
     */
    this.loginUserListener = event => {
      const url = `${Environment.fetchBaseUrl}users/login`

      // reset old AbortController and assign new one
      if (this.abortController) this.abortController.abort()
      this.abortController = new AbortController()
      // answer with event
      this.dispatchEvent(new CustomEvent('user', {
        /** @type {UserEventDetail} */
        detail: {
          fetch: fetch(url,
            {
              method: 'POST',
              ...Environment.fetchHeaders,
              body: JSON.stringify(event.detail),
              signal: this.abortController.signal
            })
            .then(response => {
              if (response.status >= 200 && response.status <= 299) return response.json()
              throw new Error(response.statusText)
            })
            .then(data => {
              if (data.errors) throw data.errors
              if (data.user) {
                this.user = data.user
                Environment.token = data.user.token
              }
              return data.user
            })
        },
        bubbles: true,
        cancelable: true,
        composed: true
      }))
    }

    this.registerUserListener = event => {
      if (!event.detail.user) return

      if (this.abortController) this.abortController.abort()
      this.abortController = new AbortController()

      const url = `${Environment.fetchBaseUrl}users`
      // answer with event
      this.dispatchEvent(new CustomEvent('user', {
        /** @type {UserEventDetail} */
        detail: {
          fetch: fetch(url,
            {
              method: 'POST',
              ...Environment.fetchHeaders,
              body: JSON.stringify(event.detail),
              signal: this.abortController.signal
            })
            .then(response => {
              if (response.status >= 200 && response.status <= 299) return response.json()
              throw new Error(response.statusText)
            })
            .then(data => {
              if (data.errors) throw data.errors
              if (data.user) {
                this.user = data.user
                Environment.token = data.user.token
              }
              return data.user
            })
        },
        bubbles: true,
        cancelable: true,
        composed: true
      }))
    }

    this.updateUserListener = event => {
      if (!event.detail.user) return

      if (this.abortController) this.abortController.abort()
      this.abortController = new AbortController()

      const url = `${Environment.fetchBaseUrl}user`
      // answer with event
      this.dispatchEvent(new CustomEvent('user', {
        /** @type {UserEventDetail} */
        detail: {
          fetch: fetch(url,
            {
              method: 'PUT',
              ...Environment.fetchHeaders,
              body: JSON.stringify(event.detail),
              signal: this.abortController.signal
            })
            .then(response => {
              if (response.status >= 200 && response.status <= 299) return response.json()
              throw new Error(response.statusText)
            })
            .then(data => {
              if (data.errors) throw data.errors
              if (data.user) {
                this.user = data.user
              }
              return data.user
            }),
          updated: true
        },
        bubbles: true,
        cancelable: true,
        composed: true
      }))
    }

    this.getUserListener = event => {
      if (this.abortController) this.abortController.abort()
      this.abortController = new AbortController()

      const url = `${Environment.fetchBaseUrl}user`
      // answer with event
      this.dispatchEvent(new CustomEvent('user', {
        /** @type {UserEventDetail} */
        detail: {
          fetch: this.user ? Promise.resolve(this.user) : Environment.token ? fetch(url,
            {
              method: 'GET',
              ...Environment.fetchHeaders,
              signal: this.abortController.signal
            })
            .then(response => {
              if (response.status >= 200 && response.status <= 299) return response.json()
              throw new Error(response.statusText)
            })
            .then(data => {
              if (data.user) {
                this.user = data.user
                Environment.token = data.user.token
              }
              return data.user
            })
            .catch(error => {
              if (error && typeof error.toString === 'function' && !error.toString().includes('aborted')) Environment.token = ''
              console.log(`Error@UserFetch: ${error}`)
            }) : Promise.reject(new Error('No token found'))
        },
        bubbles: true,
        cancelable: true,
        composed: true
      }))
    }

    this.logoutUserListener = event => {
      Environment.token = ''
      this.user = null
      this.dispatchEvent(new CustomEvent('user', {
        detail: {
          fetch: Promise.reject(new Error('User logged out'))
        },
        bubbles: true,
        cancelable: true,
        composed: true
      }))
    }

    this.getProfileListener = event => {
      if (this.abortControllerProfile) this.abortController.abort()
      this.abortControllerProfile = new AbortController()

      const url = `${Environment.fetchBaseUrl}profiles/${event.detail.username}`
      this.dispatchEvent(new CustomEvent('profile', {
        /** @type {ProfileEventDetail} */
        detail: {
          fetch: fetch(url,
            {
              method: 'GET',
              ...Environment.fetchHeaders,
              signal: this.abortControllerProfile.signal
            })
            .then(response => {
              if (response.status >= 200 && response.status <= 299) return response.json()
              throw new Error(response.statusText)
            })
            .then(data => {
              return data
            })
            .catch(error => {
              console.log(`Error@ProfileFetch: ${error}`)
            })
        },
        bubbles: true,
        cancelable: true,
        composed: true
      }))
    }
  }

  connectedCallback () {
    this.addEventListener('loginUser', this.loginUserListener)
    this.addEventListener('registerUser', this.registerUserListener)
    this.addEventListener('updateUser', this.updateUserListener)
    this.addEventListener('getUser', this.getUserListener)
    this.addEventListener('logoutUser', this.logoutUserListener)
    this.addEventListener('getProfile', this.getProfileListener)
  }

  disconnectedCallback () {
    this.removeEventListener('loginUser', this.loginUserListener)
    this.removeEventListener('registerUser', this.registerUserListener)
    this.removeEventListener('updateUser', this.updateUserListener)
    this.removeEventListener('getUser', this.getUserListener)
    this.removeEventListener('logoutUser', this.logoutUserListener)
    this.removeEventListener('getProfile', this.getProfileListener)
  }
}
