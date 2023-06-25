from typing import List, Dict, Union, Any, Callable

import param
import panel as pn
from langchain.llms import OpenAI, BaseLLM
from langchain.chains import ConversationChain
from langchain.memory import ConversationBufferMemory
from langchain.callbacks.base import BaseCallbackHandler
from langchain.schema import (
    AIMessage,
    HumanMessage,
    SystemMessage
)
from prompts import BasePromptTemplateCreator
from chat.chat_elements import TextRow, TextCodeRow
from run_time import BaseCodeRunTime
import re

pn.extension(template="bootstrap")


class StreamHandler(BaseCallbackHandler):
    """
    A handler for streaming the language model's output to a panel widget.

    Parameters
    ----------
    container : pn.widgets.ChatBox
        The chatbox container where the AI's responses will be appended.
    initial_text : str, optional
        The initial text to be displayed in the chat box.
    target_attr : str, optional
        The attribute of the container where the AI's responses will be displayed.

    """

    def __init__(self, container: pn.widgets.ChatBox,
                 initial_text: str = "",
                 target_attr: str = "value"):
        self.container = container
        self.text = initial_text
        self.target_attr = target_attr

    def on_llm_new_token(self, token: str, **kwargs) -> None:
        """
        Callback function for handling new tokens from the language model.

        Parameters
        ----------
        token : str
            The new token received from the language model.
        """
        self.text += token
        self.container.replace(-1, {"AI": [self.text]})


class LLMConversation(param.Parameterized):
    """
    A class for handling conversations with a language model.

    Parameters
    ----------
    llm : langchain.llms.BaseLLM
        The language model to use for the conversation.
    prompt_template_creator : BasePromptTemplateCreator, optional
        The prompt template creator for the conversation.
    run_time : BaseCodeRunTime, optional
        The code runtime for the conversation.
    verbose : bool, optional
        If True, print verbose output.
    """

    def __init__(self,
                 llm: BaseLLM,
                 prompt_template_creator: BasePromptTemplateCreator = None,
                 verbose: bool = False,
                 run_time: BaseCodeRunTime = None,
                 **params):
        self.run_time = run_time
        self.prompt_template_creator = prompt_template_creator
        self._llm = llm
        self._chain = ConversationChain(memory=ConversationBufferMemory(),
                                        llm=self._llm,
                                        verbose=verbose
                                        )
        # Set up the prompt template creator if one was provided
        if prompt_template_creator:
            self._chain.prompt = self.prompt_template_creator.get_prompt()

        self._spinner = pn.indicators.LoadingSpinner(value=True, width=18, height=18)
        self.chat_box = pn.widgets.ChatBox()
        self.chat_box.param.watch(self._chat, "value")

        self.end_of_response_callback = [self._code_row_callback]

    # Decorator to disable the chat box while the AI is thinking
    def _disable_inputs(func):
        async def inner(self, *args, **kwargs):
            try:
                self.chat_box.disabled = True  # Disable the chat box
                await func(self, *args, **kwargs)  # Run the decorated function
            finally:
                self.chat_box.disabled = False  # Enable the chat box when the function is done
        return inner

    @_disable_inputs
    async def _chat(self, event: Any) -> None:
        """
        Handle a chat event.

        Parameters
        ----------
        event : Any
            The chat event.
        """
        user_message = event.new[-1]
        input = user_message.get("You")
        if input is None:
            return  # If there's no input (e.g., the message was from the AI), do nothing
        self.user_row_to_textrow(input)  # convert the user row to a TextRow
        # Update the conversation chain's memory
        self.update_memory()
        
        self.chat_box.append({"AI": self._spinner})  # Show the loading spinner while the AI is generating a response
        


        # We do this every time a message is received so that the StreamHandler starts with fresh text each time
        self._llm.callbacks = [StreamHandler(self.chat_box)]
        await self._chain.apredict(input=input)

        # Run the end-of-response callbacks
        for callback in self.end_of_response_callback:
            callback()

    # Method for displaying the chat box in a Panel application

    def view(self) -> pn.widgets.ChatBox:
        """
        Return the chat box for display in a Panel application.

        Returns
        -------
        pn.widgets.ChatBox
            The chat box.
        """
        return self.chat_box.servable()  # Make the chat box servable so that it can be displayed in a Panel app

    def set_run_time(self, run_time: BaseCodeRunTime):
        self.run_time = run_time
        # update the AI TextCodeRow with the new run_time
        for message in self.chat_box.value:
            if message.get("AI", False):
                if isinstance(message["AI"][0], TextCodeRow):
                    message["AI"][0].run_time = run_time

    def set_prompt_template_creator(self, prompt_template_creator: BasePromptTemplateCreator):
        self.prompt_template_creator = prompt_template_creator
        self._chain.prompt = self.prompt_template_creator.get_prompt()

    def user_row_to_textrow(self, text):
        """
        Convert a user row to a TextRow
        """
        self.chat_box.replace(len(self.chat_box) - 1,
                              {'You': TextRow(text)})

    def _code_row_callback(self):
        """
        Check id the last message from the AI is a containing a code and if so, replace it with a TextCodeRow.
        """
        last_message = self.chat_box.value[-1]
        if not last_message.get("AI", False):
            return  # If the last message is not from the AI, do nothing

        last_message_text = last_message["AI"][0]
        # chech if the last message is a text:
        if not isinstance(last_message_text, str):
            return  # If the last message is not a string, do nothing

        # check if the last message is a code:
        if re.search(r"```", last_message_text):
            self.chat_box.replace(len(self.chat_box) - 1,
                                  {'AI': TextCodeRow(last_message_text, self.run_time)})
        else:
            self.chat_box.replace(len(self.chat_box) - 1,
                                  {'AI': TextRow(last_message_text)})

    def update_memory(self) -> None:
        """
        Update the conversation chain's memory using the chat box's chat history.

        Parameters
        ----------
        new_memory : List[Dict[str, Union[str, List[str]]]]
            The new memory to use.
        """
        # check if empty
        if len(self.chat_box.value) == 0:
            return
        
        history = []
        for row in self.chat_box.value:
            if row.get("You", False):
                history.append(HumanMessage(content=row["You"].get_information()))
            elif row.get("AI", False):
                history.append(AIMessage(content=row["AI"].get_information()))
                
        self._chain.memory.chat_memory.messages = history
