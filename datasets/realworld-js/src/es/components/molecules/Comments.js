// @ts-check

/* global CustomEvent */
/* global HTMLElement */

import { secureImageSrc } from '../../helpers/Utils.js'

/**
 * https://github.com/Weedshaker/event-driven-web-components-realworld-example-app/blob/master/FRONTEND_INSTRUCTIONS.md#home
 * As a molecule, this component shall hold Atoms
 *
 * @export
 * @class Comments
 */
export default class Comments extends HTMLElement {
  constructor () {
    super()

    /**
     * Listens to the event name/typeArg: 'comment'
     *
     * @param {CustomEvent & {detail: import("../controllers/Comments.js").CommentsEventDetail}} event
     */
    this.commentListener = event => event.detail.fetch.then(({ comment }) => {
      this.insertBefore(this.createComment(comment, false), this.firstCard)
      this.formControl.value = ''
    })

    /**
     * Listens to the event name/typeArg: 'comments'
     * which is returned when adding a comment
     *
     * @param {CustomEvent & {detail: import("../controllers/Comments.js").CommentEventDetail}} event
     */
    this.commentsListener = event => this.render(event.detail.fetch)

    /**
     * target href to dispatch a CustomEvent requestListArticles, which will trigger ListArticlePreviews to render with new query
     *
     * @param {event & {target: HTMLElement}} event
     * @return {void | false}
     */
    this.clickListener = event => {
      let isDeleteIcon = false
      if (!event.target || (event.target.tagName !== 'BUTTON' && !(isDeleteIcon = event.target.classList.contains('ion-trash-a')))) return false
      event.preventDefault()
      if (isDeleteIcon) {
        const card = event.target.parentNode.parentNode.parentNode
        if (card && card.classList.contains('card')) {
          this.dispatchEvent(new CustomEvent('deleteComment', {
            /** @type {import("../controllers/Comments.js").DeleteCommentEventDetail} */
            detail: {
              id: card.getAttribute('id')
            },
            bubbles: true,
            cancelable: true,
            composed: true
          }))
          card.remove()
        }
      } else {
        if (this.formControl.value) {
          this.dispatchEvent(new CustomEvent('addComment', {
          /** @type {import("../controllers/Comments.js").AddCommentsEventDetail} */
            detail: {
              body: this.formControl.value
            },
            bubbles: true,
            cancelable: true,
            composed: true
          }))
        }
      }
    }
  }

  connectedCallback () {
    // listen for comments
    document.body.addEventListener('comments', this.commentsListener)
    document.body.addEventListener('comment', this.commentListener)
    this.addEventListener('click', this.clickListener)
    // on every connect it will attempt to get newest comments
    this.dispatchEvent(new CustomEvent('getComments', {
      bubbles: true,
      cancelable: true,
      composed: true
    }))
    if (this.shouldComponentRender()) this.render(null)
  }

  disconnectedCallback () {
    document.body.removeEventListener('comments', this.commentsListener)
    document.body.removeEventListener('comment', this.commentListener)
    this.removeEventListener('click', this.clickListener)
  }

  /**
   * evaluates if a render is necessary
   *
   * @return {boolean}
   */
  shouldComponentRender () {
    return !this.innerHTML
  }

  /**
   * renders each received comment
   *
   * @param {Promise<import("../../helpers/Interfaces.js").MultipleComments> | null} fetchComments
   * @return {void}
   */
  render (fetchComments) {
    this.innerHTML = /* html */ `
      <form class="card comment-form">
        <div class="card-block">
          <textarea class="form-control" placeholder="Write a comment..." rows="3"></textarea>
        </div>
        <div class="card-footer">
          <img src="${secureImageSrc(this.getAttribute('user-image')) || ''}" class="comment-author-img" />
          <button class="btn btn-sm btn-primary">
          Post Comment
          </button>
        </div>
      </form>
    `
    fetchComments && fetchComments.then(({ comments }) => {
      this.innerHTML += comments.reduce((commentsStr, comment) => (commentsStr += this.createComment(comment)), '')
    })
  }

  /**
   * html snipper for comment to be filled
   *
   * @param {import("../../helpers/Interfaces.js").SingleComment} comment
   * @param {boolean} [returnString = true]
   * @return {string | Node}
   */
  createComment (comment, returnString = true) {
    const card = /* html */`
      <div class="card" id="${comment.id}">
        <div class="card-block">
          <p class="card-text">${comment.body}</p>
        </div>
        <div class="card-footer">
          <a href="" class="comment-author">
            <img src="${secureImageSrc(comment.author.image)}" class="comment-author-img" />
          </a>
          &nbsp;
          <a href="#/profile/${comment.author.username}" class="comment-author">${comment.author.username}</a>
          <span class="date-posted">${new Date(comment.createdAt).toDateString()}</span>
          ${comment.author.username === this.getAttribute('user-name') ? '<span class="mod-options"><i class="ion-trash-a"></i></span>' : ''}
        </div>
      </div>
    `
    if (returnString) return card
    const div = document.createElement('div')
    div.innerHTML = card
    return div.children[0]
  }

  get formControl () {
    return this.querySelector('.form-control')
  }

  /**
   * returns the first card element
   *
   * @readonly
   * @return {HTMLElement}
   */
  get firstCard () {
    return this.querySelector('.card:not(.comment-form)')
  }
}
