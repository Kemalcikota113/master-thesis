// @ts-check

/* global HTMLElement */
/* global AbortController */
/* global CustomEvent */
/* global fetch */

/**
 * https://github.com/gothinkster/realworld/tree/master/api#add-comments-to-an-article
 *
 * @typedef {{ slug?: string, body: string }} AddCommentsEventDetail
 */

/**
 * https://github.com/gothinkster/realworld/tree/master/api#add-comments-to-an-article
 *
 * @typedef {{
  fetch: Promise<import("../../helpers/Interfaces.js").SingleComment>
}} CommentEventDetail
*/

/**
 * https://github.com/gothinkster/realworld/tree/master/api#get-comments-from-an-article
 *
 * @typedef {{ slug?: string }} GetCommentsEventDetail
 */

/**
 * https://github.com/gothinkster/realworld/tree/master/api#get-comments-from-an-article
 *
 * @typedef {{
      fetch: Promise<import("../../helpers/Interfaces.js").MultipleComments>
    }} CommentsEventDetail
 */

/**
 * https://github.com/gothinkster/realworld/tree/master/api#delete-comment
 *
 * @typedef {{ slug?: string, id: string }} DeleteCommentEventDetail
 */

import { Environment } from '../../helpers/Environment.js'

/**
 * https://github.com/gothinkster/realworld/tree/master/api#add-comments-to-an-article
 * As a controller, this component becomes a store and organizes events
 * dispatches: 'comment' on 'addComment'
 * dispatches: 'comments' on 'getComments'
 * does nothing on 'deleteComment'
 *
 * @export
 * @class Comments
 */
export default class Comments extends HTMLElement {
  constructor () {
    super()

    /**
     * Used to cancel ongoing, older fetches
     * this makes sense, if you only expect one and most recent true result and not multiple
     *
     * @type {AbortController | null}
     */
    this.abortController = null

    /**
     * Listens to the event name/typeArg: 'addComment'
     *
     * @param {CustomEvent & {detail: AddCommentsEventDetail}} event
     */
    this.addCommentListener = event => {
      // if no slug is sent, we grab it here from the location, this logic could also be handle through an event at the router
      const slug = (event.detail && event.detail.slug) || Environment.slug || ''
      const url = `${Environment.fetchBaseUrl}articles/${slug}/comments`
      // reset old AbortController and assign new one
      if (this.abortController) this.abortController.abort()
      this.abortController = new AbortController()
      // answer with event
      this.dispatchEvent(new CustomEvent('comment', {
        /** @type {CommentEventDetail} */
        detail: {
          fetch: fetch(url, {
            method: 'POST',
            body: JSON.stringify({ comment: { body: event.detail.body } }),
            signal: this.abortController.signal,
            ...Environment.fetchHeaders
          }).then(response => {
            if (response.status >= 200 && response.status <= 299) return response.json()
            throw new Error(response.statusText)
          // @ts-ignore
          })
        },
        bubbles: true,
        cancelable: true,
        composed: true
      }))
    }

    /**
     * Listens to the event name/typeArg: 'getComments'
     *
     * @param {CustomEvent & {detail: GetCommentsEventDetail}} event
     */
    this.getCommentsListener = event => {
      // if no slug is sent, we grab it here from the location, this logic could also be handle through an event at the router
      const slug = (event.detail && event.detail.slug) || Environment.slug || ''
      const url = `${Environment.fetchBaseUrl}articles/${slug}/comments`
      // reset old AbortController and assign new one
      if (this.abortController) this.abortController.abort()
      this.abortController = new AbortController()
      // answer with event
      this.dispatchEvent(new CustomEvent('comments', {
        /** @type {CommentsEventDetail} */
        detail: {
          fetch: fetch(url, {
            signal: this.abortController.signal,
            ...Environment.fetchHeaders
          }).then(response => {
            if (response.status >= 200 && response.status <= 299) return response.json()
            throw new Error(response.statusText)
          // @ts-ignore
          })
        },
        bubbles: true,
        cancelable: true,
        composed: true
      }))
    }

    /**
     * Listens to the event name/typeArg: 'deleteComment'
     *
     * @param {CustomEvent & {detail: DeleteCommentEventDetail}} event
     */
    this.deleteCommentListener = event => {
      // if no slug is sent, we grab it here from the location, this logic could also be handle through an event at the router
      const slug = (event.detail && event.detail.slug) || Environment.slug || ''
      const url = `${Environment.fetchBaseUrl}articles/${slug}/comments/${event.detail.id}`
      fetch(url, {
        method: 'DELETE',
        ...Environment.fetchHeaders
      }).then(response => {
        if (response.status >= 200 && response.status <= 299) return
        throw new Error(response.statusText)
      // @ts-ignore
      })
    }
  }

  connectedCallback () {
    this.addEventListener('addComment', this.addCommentListener)
    this.addEventListener('getComments', this.getCommentsListener)
    this.addEventListener('deleteComment', this.deleteCommentListener)
  }

  disconnectedCallback () {
    this.removeEventListener('addComment', this.addCommentListener)
    this.removeEventListener('getComments', this.getCommentsListener)
    this.removeEventListener('deleteComment', this.deleteCommentListener)
  }
}
